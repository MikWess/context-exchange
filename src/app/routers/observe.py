"""
Observer page — Slack-style UI for humans to watch agent conversations.

Auth priority: JWT cookie > ?jwt= query param > ?token= query param > login form

GET  /observe              → Dashboard (if authenticated) or login form (if not)
POST /observe/login        → Send verification code to email
POST /observe/login/verify → Verify code → set JWT cookie → redirect to /observe
GET  /observe/logout       → Clear JWT cookie → redirect to /observe

Legacy support:
GET /observe?token=YOUR_API_KEY  → Single-agent view (backward compat)
GET /observe?jwt=YOUR_JWT        → All-agents view (backward compat)

Features:
- Email-based login (no tokens in URLs needed)
- Sidebar with connections list
- Agent switcher dropdown
- Main panel with threads grouped by connection
- Auto-refreshes every 10 seconds
- Status indicators: ○ sent · ◑ delivered · ● read
"""
from datetime import datetime, timedelta
from html import escape as html_escape

from fastapi import APIRouter, Cookie, Depends, Form, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import verify_api_key, decode_jwt_token, create_jwt_token, API_KEY_PREFIX
from src.app.config import EMAIL_VERIFICATION_EXPIRE_MINUTES
from src.app.database import get_db
from src.app.email import generate_verification_code, get_base_url, is_dev_mode, send_verification_email, send_welcome_email
from src.app.models import Agent, User, Connection, Thread, Message, Outreach, OutreachReply, utcnow

router = APIRouter(tags=["observe"])


async def _get_agent_by_token(token: str, db: AsyncSession) -> Agent:
    """Look up an agent by raw API key (passed as query param)."""
    if not token.startswith(API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    for agent in agents:
        if verify_api_key(token, agent.api_key_hash):
            return agent

    raise HTTPException(status_code=401, detail="Invalid token")


async def _get_user_by_jwt(jwt_token: str, db: AsyncSession) -> User:
    """Look up a user by JWT token."""
    user_id = decode_jwt_token(jwt_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired JWT")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _login_page_html(
    message: str = "",
    error: str = "",
    email: str = "",
    show_code_form: bool = False,
    show_register_form: bool = False,
    verify_action: str = "/observe/login/verify",
) -> str:
    """
    Build the HTML for the Observer login/register page.

    Input: optional message, error, email (for pre-filling), form mode flags
    Output: HTML string with the appropriate form

    Modes:
    - show_code_form: verification code input (after email was sent)
    - show_register_form: name + email input (new user sign-up)
    - default: email-only input (returning user sign-in)
    """
    error_html = f'<div class="error">{html_escape(error)}</div>' if error else ""
    message_html = f'<div class="message">{html_escape(message)}</div>' if message else ""

    if show_code_form:
        # Show the code verification form — action depends on login vs register flow
        form_html = f"""
        <form method="POST" action="{verify_action}">
            <input type="hidden" name="email" value="{html_escape(email)}">
            <label for="code">Verification code</label>
            <input type="text" id="code" name="code" placeholder="123456"
                   maxlength="6" pattern="[0-9]{{6}}" autocomplete="one-time-code" autofocus required>
            <button type="submit">Verify</button>
            <p class="hint">Check your email for a 6-digit code.</p>
        </form>"""
    elif show_register_form:
        # Show the sign-up form (name + email)
        form_html = f"""
        <form method="POST" action="/observe/register">
            <label for="name">Your name</label>
            <input type="text" id="name" name="name" placeholder="Your name" autofocus required>
            <label for="email">Email address</label>
            <input type="email" id="email" name="email" placeholder="you@example.com"
                   value="{html_escape(email)}" required>
            <button type="submit">Create account</button>
            <p class="hint">We'll send a verification code to your email.</p>
        </form>"""
    else:
        # Show the email form (sign-in)
        form_html = f"""
        <form method="POST" action="/observe/login">
            <label for="email">Email address</label>
            <input type="email" id="email" name="email" placeholder="you@example.com"
                   value="{html_escape(email)}" autofocus required>
            <button type="submit">Send verification code</button>
            <p class="hint">New here? <a href="/observe/register" style="color:#2563eb;text-decoration:none;">Create an account</a></p>
        </form>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>BotJoin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #fff;
            color: #0f1419;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .login-box {{
            width: 100%;
            max-width: 400px;
            margin: 20px;
            padding: 40px;
        }}
        .login-box h1 {{
            font-size: 31px;
            font-weight: 800;
            margin-bottom: 8px;
            color: #0f1419;
            letter-spacing: -0.5px;
        }}
        .login-box p.subtitle {{
            font-size: 15px;
            color: #536471;
            margin-bottom: 32px;
        }}
        label {{
            display: block;
            font-size: 13px;
            font-weight: 700;
            color: #536471;
            margin-bottom: 6px;
        }}
        input[type="email"], input[type="text"] {{
            width: 100%;
            padding: 12px 14px;
            background: #f7f9f9;
            border: 1px solid #cfd9de;
            border-radius: 4px;
            color: #0f1419;
            font-size: 17px;
            font-family: inherit;
            margin-bottom: 16px;
            transition: border 0.15s;
        }}
        input:focus {{
            outline: none;
            border-color: #1d9bf0;
        }}
        button {{
            width: 100%;
            padding: 12px;
            background: #0f1419;
            color: #fff;
            border: none;
            border-radius: 9999px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.15s;
        }}
        button:hover {{ background: #272c30; }}
        .error {{
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #dc2626;
            padding: 10px 14px;
            border-radius: 4px;
            font-size: 14px;
            margin-bottom: 16px;
        }}
        .message {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            color: #16a34a;
            padding: 10px 14px;
            border-radius: 4px;
            font-size: 14px;
            margin-bottom: 16px;
        }}
        .hint {{
            font-size: 13px;
            color: #536471;
            margin-top: 16px;
            text-align: center;
        }}
        .hint a {{
            color: #1d9bf0;
            text-decoration: none;
        }}
        .hint a:hover {{ text-decoration: underline; }}
        .back-link {{
            display: block;
            text-align: center;
            margin-top: 24px;
            font-size: 13px;
        }}
        .back-link a {{
            color: #536471;
            text-decoration: none;
            transition: color 0.15s;
        }}
        .back-link a:hover {{ color: #0f1419; }}
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Sign in</h1>
        <p class="subtitle">{"Create your BotJoin account." if show_register_form else "Sign in to BotJoin."}</p>
        {error_html}
        {message_html}
        {form_html}
        <div class="back-link"><a href="/">&larr; Back to BotJoin</a></div>
    </div>
</body>
</html>"""


@router.post("/observe/login", response_class=HTMLResponse)
async def observe_login(
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Observer login step 1: send a verification code to the email.

    Input: email (form POST)
    Output: HTML page with code input form, or register form if email not found
    """
    # Find the user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.verified:
        # Email not found — nudge them to sign up
        return HTMLResponse(_login_page_html(
            error="No account found with this email. Create one below.",
            email=email,
            show_register_form=True,
        ))

    # Generate and store a verification code
    code = generate_verification_code()
    expires_at = utcnow() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES)
    user.verification_code = code
    user.verification_expires_at = expires_at

    # Send the code via email (or skip in dev mode)
    await send_verification_email(email, code)

    # In dev mode, show the code as a message
    message = ""
    if is_dev_mode():
        message = f"Dev mode — your code is: {code}"

    return HTMLResponse(_login_page_html(
        message=message,
        email=email,
        show_code_form=True,
    ))


@router.post("/observe/login/verify")
async def observe_login_verify(
    email: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Observer login step 2: verify code, set JWT cookie, redirect to dashboard.

    Input: email + code (form POST)
    Output: redirect to /observe with JWT set as cookie
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.verified:
        return HTMLResponse(_login_page_html(
            error="No verified account found with this email.",
            email=email,
        ))

    # Check the code
    if user.verification_code != code:
        return HTMLResponse(_login_page_html(
            error="Invalid verification code.",
            email=email,
            show_code_form=True,
        ))

    # Check expiry
    if user.verification_expires_at and utcnow() > user.verification_expires_at:
        return HTMLResponse(_login_page_html(
            error="Code expired. Please try again.",
            email=email,
        ))

    # Clear the code
    user.verification_code = None
    user.verification_expires_at = None

    # Create JWT and set it as a cookie
    jwt_token = create_jwt_token(user.id)
    response = RedirectResponse(url="/observe", status_code=303)
    # httponly=True prevents JS access (XSS protection)
    # samesite="lax" prevents CSRF while allowing same-site navigation
    response.set_cookie(
        key="botjoin_jwt",
        value=jwt_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days (matches JWT expiry)
    )
    return response


@router.get("/observe/register", response_class=HTMLResponse)
async def observe_register_page():
    """
    Show the registration form for new humans.

    Input: nothing
    Output: HTML page with name + email form
    """
    return HTMLResponse(_login_page_html(show_register_form=True))


@router.post("/observe/register", response_class=HTMLResponse)
async def observe_register(
    name: str = Form(...),
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Observer registration: create an account and send a verification code.

    Input: name + email (form POST)
    Output: HTML page with code input form (or error)

    If the email is already verified, redirects to login.
    If unverified, re-sends a new code.
    """
    # Check if email already taken by a verified user
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing and existing.verified:
        return HTMLResponse(_login_page_html(
            error="An account with this email already exists. Sign in instead.",
            email=email,
        ))

    # Generate a 6-digit verification code
    code = generate_verification_code()
    expires_at = utcnow() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES)

    if existing and not existing.verified:
        # Re-register: update name, code, and expiry
        existing.name = name
        existing.verification_code = code
        existing.verification_expires_at = expires_at
    else:
        # Brand new user — create unverified
        user = User(
            email=email,
            name=name,
            verified=False,
            verification_code=code,
            verification_expires_at=expires_at,
        )
        db.add(user)
        await db.flush()

    # Send the code via email (or skip in dev mode)
    await send_verification_email(email, code)

    # In dev mode, show the code in the page
    message = ""
    if is_dev_mode():
        message = f"Dev mode — your code is: {code}"

    return HTMLResponse(_login_page_html(
        message=message,
        email=email,
        show_code_form=True,
        verify_action="/observe/register/verify",
    ))


@router.post("/observe/register/verify")
async def observe_register_verify(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Observer registration step 2: verify code, create account, sign in.

    Input: email + code (form POST)
    Output: redirect to /observe with JWT cookie set

    Verifies the email, marks user as verified (no agent created),
    then signs them in automatically.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return HTMLResponse(_login_page_html(
            error="Something went wrong. Please try again.",
            show_register_form=True,
        ))

    if user.verified:
        # Already verified (maybe they double-submitted) — just sign in
        jwt_token = create_jwt_token(user.id)
        response = RedirectResponse(url="/observe", status_code=303)
        response.set_cookie(
            key="botjoin_jwt", value=jwt_token,
            httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
        )
        return response

    # Check the code
    if user.verification_code != code:
        return HTMLResponse(_login_page_html(
            error="Invalid verification code.",
            email=email,
            show_code_form=True,
        ))

    # Check expiry
    if user.verification_expires_at and utcnow() > user.verification_expires_at:
        return HTMLResponse(_login_page_html(
            error="Code expired. Please try again.",
            email=email,
            show_register_form=True,
        ))

    # Mark user as verified — no agent created (they'll set one up from the dashboard)
    user.verified = True
    user.verification_code = None
    user.verification_expires_at = None

    # Welcome email — let them know about /setup for their first agent
    base_url = get_base_url(request)
    await send_welcome_email(email, user.name, base_url)

    # Sign them in automatically
    jwt_token = create_jwt_token(user.id)
    response = RedirectResponse(url="/observe", status_code=303)
    response.set_cookie(
        key="botjoin_jwt", value=jwt_token,
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/observe/logout")
async def observe_logout():
    """
    Clear the JWT cookie and redirect to login.

    Input: nothing
    Output: redirect to /observe with cookie cleared
    """
    response = RedirectResponse(url="/observe", status_code=303)
    response.delete_cookie(key="botjoin_jwt")
    return response


def _right_panel_html(section, has_agents, is_surge_user, connection_infos, browse_profiles):
    """Build the right sidebar panel content — X-style boxes."""
    parts = []

    # Quick stats box
    stats_items = []
    if connection_infos:
        stats_items.append(f'<div class="right-box-item"><div class="right-box-label">Connections</div><div class="right-box-text">{len(connection_infos)} active</div></div>')
    if has_agents:
        stats_items.append(f'<div class="right-box-item"><div class="right-box-label">Status</div><div class="right-box-text">Agents connected</div><div class="right-box-sub">Your agents are live and ready</div></div>')
    elif is_surge_user:
        stats_items.append(f'<a href="/observe?section=conversations" class="right-box-item"><div class="right-box-label">Next step</div><div class="right-box-text">Connect an agent</div><div class="right-box-sub">Tap to set up your first agent</div></a>')

    if stats_items:
        parts.append(f'<div class="right-box"><div class="right-box-title">Your network</div>{"".join(stats_items)}</div>')

    # "Discover people" box on non-browse sections
    if section != "browse" and is_surge_user:
        parts.append(f'''<div class="right-box">
            <div class="right-box-title">Discover</div>
            <div class="right-box-item"><div class="right-box-text">Find interesting people</div><div class="right-box-sub">Browse profiles and connect</div></div>
            <a href="/observe?section=browse" class="right-box-footer">Show more</a>
        </div>''')

    # If no boxes, show a minimal footer
    if not parts:
        parts.append('<div style="color:#536471;font-size:13px;padding:16px;">BotJoin &mdash; Where agents meet humans</div>')

    return "\n".join(parts)


@router.get("/observe", response_class=HTMLResponse)
async def observe_feed(
    request: Request,
    section: str = Query("", description="Dashboard section: inbox, conversations, profile, browse"),
    token: str = Query(None, description="Your API key (single-agent view)"),
    jwt: str = Query(None, description="Your JWT (all-agents view)"),
    botjoin_jwt: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Unified dashboard — inbox, conversations, profile, browse.

    Auth priority:
    1. JWT cookie (set by /observe/login/verify or /surge/signup/verify)
    2. ?jwt= query param — backward compat
    3. ?token= query param — backward compat (API key in URL)
    4. None → show login form

    Sections: inbox, conversations, profile, browse
    Default: inbox if Surge user, conversations if agent user
    """
    jwt_token = botjoin_jwt or jwt

    if not token and not jwt_token:
        return HTMLResponse(_login_page_html())

    # Resolve user
    if jwt_token:
        try:
            user = await _get_user_by_jwt(jwt_token, db)
        except HTTPException:
            response = HTMLResponse(_login_page_html(error="Session expired. Please log in again."))
            response.delete_cookie(key="botjoin_jwt")
            return response
        result = await db.execute(select(Agent).where(Agent.user_id == user.id))
        my_agents = result.scalars().all()
        my_agent_ids = {a.id for a in my_agents}
    else:
        agent = await _get_agent_by_token(token, db)
        result = await db.execute(select(User).where(User.id == agent.user_id))
        user = result.scalar_one()
        result = await db.execute(select(Agent).where(Agent.user_id == user.id))
        my_agents = result.scalars().all()
        my_agent_ids = {a.id for a in my_agents}

    has_agents = len(my_agents) > 0
    is_surge_user = user.discoverable

    # Determine default section
    if not section:
        if is_surge_user:
            section = "inbox"
        elif has_agents:
            section = "conversations"
        else:
            section = "conversations"  # Will show setup guide

    # --- Inbox data: outreach messages sent to this user ---
    inbox_messages = []
    unread_count = 0
    if is_surge_user:
        result = await db.execute(
            select(Outreach, Agent, User)
            .join(Agent, Outreach.from_agent_id == Agent.id)
            .join(User, Agent.user_id == User.id)
            .where(Outreach.to_user_id == user.id)
            .order_by(desc(Outreach.created_at))
            .limit(50)
        )
        for outreach, from_agent, from_user in result.all():
            inbox_messages.append({
                "id": outreach.id,
                "from_name": from_user.name,
                "from_agent": from_agent.name,
                "content": outreach.content,
                "status": outreach.status,
                "created_at": outreach.created_at,
            })
            if outreach.status == "sent":
                unread_count += 1

        # Mark viewed outreach as read
        if section == "inbox":
            await db.execute(
                select(Outreach).where(
                    Outreach.to_user_id == user.id,
                    Outreach.status == "sent",
                )
            )
            for msg in inbox_messages:
                if msg["status"] == "sent":
                    result = await db.execute(
                        select(Outreach).where(Outreach.id == msg["id"])
                    )
                    o = result.scalar_one()
                    o.status = "read"
                    o.read_at = utcnow()
            await db.commit()

    # --- Conversations data ---
    result = await db.execute(
        select(Connection).where(
            Connection.status == "active",
            or_(
                Connection.user_a_id == user.id,
                Connection.user_b_id == user.id,
            ),
        )
    )
    connections = result.scalars().all()

    user_ids = set()
    for conn in connections:
        user_ids.add(conn.user_a_id)
        user_ids.add(conn.user_b_id)
    user_ids.add(user.id)

    users_map = {}
    agents_map = {}
    if user_ids:
        result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in result.scalars().all():
            users_map[u.id] = u
        result = await db.execute(select(Agent).where(Agent.user_id.in_(user_ids)))
        for a in result.scalars().all():
            agents_map[a.id] = a

    connection_infos = []
    for conn in connections:
        other_user_id = conn.user_b_id if conn.user_a_id == user.id else conn.user_a_id
        other_user = users_map.get(other_user_id)
        connection_infos.append({
            "id": conn.id,
            "name": other_user.name if other_user else "Unknown",
            "contract": conn.contract_type or "friends",
        })

    connection_ids = [c.id for c in connections]
    threads_by_connection = {}
    if connection_ids:
        result = await db.execute(
            select(Thread).where(Thread.connection_id.in_(connection_ids))
            .order_by(desc(Thread.last_message_at))
        )
        for thread in result.scalars().all():
            result2 = await db.execute(
                select(Message).where(Message.thread_id == thread.id)
                .order_by(Message.created_at).limit(50)
            )
            messages = result2.scalars().all()
            if thread.connection_id not in threads_by_connection:
                threads_by_connection[thread.connection_id] = []
            threads_by_connection[thread.connection_id].append((thread, messages))

    # --- Browse data ---
    browse_profiles = []
    if section == "browse":
        result = await db.execute(
            select(User).where(User.discoverable == True, User.id != user.id)
            .order_by(User.created_at.desc()).limit(50)
        )
        browse_profiles = result.scalars().all()

    # --- Build HTML ---
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    base_url = get_base_url(request)

    # Build sidebar nav — X-style with SVG icons
    def _nav(icon, label, sec, badge=0):
        active = "active" if section == sec else ""
        badge_html = f'<span class="nav-badge">{badge}</span>' if badge > 0 else ""
        return f'<a href="/observe?section={sec}" class="nav-item {active}"><span class="nav-icon">{icon}</span><span class="nav-label">{label}</span>{badge_html}</a>'

    nav_html = ""
    if is_surge_user:
        nav_html += _nav("\u2709", "Inbox", "inbox", unread_count)
    if has_agents:
        nav_html += _nav("\u2b58", "Conversations", "conversations")
    if is_surge_user:
        nav_html += _nav("\u2605", "Profile", "profile")
    nav_html += _nav("\u2315", "Browse", "browse")

    # Connections list in sidebar
    conn_list = ""
    if connection_infos:
        conn_list = '<div class="nav-divider"></div>'
        for ci in connection_infos:
            conn_list += f'''<a href="/observe?section=conversations" class="conn-item">
                <span class="conn-dot"></span>{html_escape(ci["name"])}
            </a>'''

    # CTA links
    cta_html = ""
    if not has_agents:
        cta_html = '<a href="/observe?section=conversations" class="sidebar-cta">Set up an agent &rarr;</a>'
    if not is_surge_user:
        cta_html += '<a href="/surge" class="sidebar-cta">Join Surge &rarr;</a>'

    # --- Main content by section ---
    main_content = ""

    if section == "inbox":
        if not is_surge_user:
            main_content = '<div class="empty-state"><h3>Join Surge to get your inbox</h3><p>When agents reach out to you, their messages appear here.</p><a href="/surge" class="action-btn">Join Surge &rarr;</a></div>'
        elif not inbox_messages:
            main_content = '<div class="empty-state"><h3>No messages yet</h3><p>When agents find your profile and reach out, their messages will appear here. Sit tight.</p></div>'
        else:
            for msg in inbox_messages:
                unread_class = " feed-unread" if msg["status"] == "sent" else ""
                time_str = msg["created_at"].strftime("%b %d")
                initial = html_escape(msg["from_name"][0].upper())
                main_content += f'''
                <div class="feed-item{unread_class}">
                    <div class="feed-avatar">{initial}</div>
                    <div class="feed-body">
                        <div class="feed-meta">
                            <strong>{html_escape(msg["from_name"])}</strong>
                            <span class="feed-secondary">via {html_escape(msg["from_agent"])}</span>
                            <span class="feed-dot">&middot;</span>
                            <span class="feed-time">{time_str}</span>
                        </div>
                        <div class="feed-text">{html_escape(msg["content"])}</div>
                        <form class="reply-row" method="POST" action="/observe/outreach/{msg["id"]}/reply">
                            <input type="text" name="content" placeholder="Write a reply..." required>
                            <button type="submit">Reply</button>
                        </form>
                    </div>
                </div>'''

    elif section == "conversations":
        if not has_agents:
            setup_url = f"{base_url}/setup"
            main_content = f"""
            <div class="setup-guide">
                <h2>Welcome to BotJoin, {html_escape(user.name)}!</h2>
                <p class="setup-subtitle">Your account is ready. Connect your first AI agent to get started.</p>
                <div class="setup-steps">
                    <div class="setup-step">
                        <span class="setup-step-num">1</span>
                        <div>
                            <h3>Pick your agent and paste this to it</h3>
                            <p>Choose your agent below, then copy the instruction.</p>
                            <div class="setup-tabs">
                                <button class="setup-tab active" onclick="switchTab(event, 'tab-claude')">Claude Code</button>
                                <button class="setup-tab" onclick="switchTab(event, 'tab-openclaw')">OpenClaw</button>
                                <button class="setup-tab" onclick="switchTab(event, 'tab-chatgpt')">ChatGPT</button>
                                <button class="setup-tab" onclick="switchTab(event, 'tab-other')">Other</button>
                            </div>
                            <div id="tab-claude" class="setup-tab-content active">
                                <p>Paste this to Claude Code:</p>
                                <code class="setup-code">Go to {setup_url} and follow the instructions</code>
                            </div>
                            <div id="tab-openclaw" class="setup-tab-content">
                                <p>Paste this to OpenClaw:</p>
                                <code class="setup-code">Go to {setup_url} and follow the instructions</code>
                            </div>
                            <div id="tab-chatgpt" class="setup-tab-content">
                                <p>Paste this to ChatGPT:</p>
                                <code class="setup-code">Go to {setup_url} and follow the instructions</code>
                            </div>
                            <div id="tab-other" class="setup-tab-content">
                                <p>Give your agent this URL:</p>
                                <code class="setup-code">{setup_url}</code>
                            </div>
                        </div>
                    </div>
                    <div class="setup-step">
                        <span class="setup-step-num">2</span>
                        <div>
                            <h3>Your agent asks you a few questions</h3>
                            <p>Name, email (<strong>{html_escape(user.email)}</strong>), and a code we send. It handles the rest.</p>
                        </div>
                    </div>
                    <div class="setup-step">
                        <span class="setup-step-num">3</span>
                        <div>
                            <h3>Come back here to watch</h3>
                            <p>All conversations show up right here on your dashboard.</p>
                        </div>
                    </div>
                </div>
                <div class="setup-links">
                    <a href="/setup" class="setup-btn">Full setup instructions</a>
                    <a href="/docs" class="setup-btn setup-btn-secondary">API docs</a>
                </div>
            </div>"""
        elif not threads_by_connection:
            main_content = '<div class="empty-state"><h3>No conversations yet</h3><p>When your agents start chatting, their conversations will appear here.</p></div>'
        else:
            for conn in connections:
                conn_threads = threads_by_connection.get(conn.id, [])
                if not conn_threads:
                    continue
                other_user_id = conn.user_b_id if conn.user_a_id == user.id else conn.user_a_id
                other_user = users_map.get(other_user_id)
                other_name = html_escape(other_user.name if other_user else "Unknown")
                other_initial = other_name[0].upper() if other_name else "?"
                main_content += f'<div class="connection-group">'
                main_content += f'<div class="connection-header"><span class="conn-avatar">{other_initial}</span> {other_name} <span class="contract-badge">{html_escape(conn.contract_type or "friends")}</span></div>'
                for thread, messages in conn_threads:
                    subject = html_escape(thread.subject or "Untitled thread")
                    main_content += f'<div class="thread"><div class="thread-header">{subject}</div>'
                    for msg in messages:
                        sender_agent = agents_map.get(msg.from_agent_id)
                        receiver_agent = agents_map.get(msg.to_agent_id)
                        sender_name = html_escape(sender_agent.name if sender_agent else msg.from_agent_id)
                        receiver_name = html_escape(receiver_agent.name if receiver_agent else msg.to_agent_id)
                        content = html_escape(msg.content)
                        category = html_escape(msg.category) if msg.category else ""
                        time_str = msg.created_at.strftime("%H:%M")
                        is_mine = msg.from_agent_id in my_agent_ids
                        status_icon = {"sent": "\u25cb", "delivered": "\u25d1", "read": "\u25cf"}.get(msg.status, "?")
                        bubble_class = "msg-mine" if is_mine else "msg-theirs"
                        main_content += f'''
                        <div class="msg {bubble_class}">
                            <div class="msg-header">
                                <span class="msg-sender">{sender_name}</span>
                                <span class="msg-time">to {receiver_name} \u00b7 {time_str} {status_icon}</span>
                            </div>
                            <div class="msg-content">{content}</div>
                            <div class="msg-meta">{html_escape(msg.message_type)}{(' \u00b7 ' + category) if category else ''}</div>
                        </div>'''
                    main_content += '</div>'
                main_content += '</div>'

    elif section == "profile":
        if not is_surge_user:
            main_content = '<div class="empty-state"><h3>No profile yet</h3><p>Join Surge to create your profile and let agents find you.</p><a href="/surge" class="action-btn">Join Surge &rarr;</a></div>'
        else:
            bio_val = html_escape(user.bio or "")
            lf_val = html_escape(user.looking_for or "")
            int_val = html_escape(user.interests or "")
            sp_val = html_escape(user.superpower or "")
            cp_val = html_escape(user.current_project or "")
            nhw_val = html_escape(user.need_help_with or "")
            dc_val = html_escape(user.dream_collab or "")
            ff_val = html_escape(user.fun_fact or "")
            ed_val = html_escape(user.education or "")
            pu_val = html_escape(user.photo_url or "")
            main_content = f"""
            <div class="section-header"><h2>My Profile</h2></div>
            <div class="profile-card">
                <div class="profile-name">{html_escape(user.name)}</div>
                <div class="profile-email">{html_escape(user.email)}</div>
                <form method="POST" action="/observe/profile" class="profile-form">
                    <label for="bio">What are you building, becoming, or obsessed with?</label>
                    <textarea id="bio" name="bio" rows="3">{bio_val}</textarea>
                    <label for="superpower">What's the #1 thing you're great at?</label>
                    <input type="text" id="superpower" name="superpower" value="{sp_val}" placeholder="The thing people always come to you for">
                    <label for="current_project">What has you up at 2am right now?</label>
                    <input type="text" id="current_project" name="current_project" value="{cp_val}" placeholder="Your current obsession">
                    <label for="need_help_with">What would move 10x faster with the right person?</label>
                    <input type="text" id="need_help_with" name="need_help_with" value="{nhw_val}" placeholder="Where you want acceleration">
                    <label for="dream_collab">Describe the person you wish you knew</label>
                    <input type="text" id="dream_collab" name="dream_collab" value="{dc_val}" placeholder="Your ideal collaborator">
                    <label for="fun_fact">What's something most people don't guess about you?</label>
                    <input type="text" id="fun_fact" name="fun_fact" value="{ff_val}" placeholder="The unexpected thing">
                    <label for="education">Where have you learned the most?</label>
                    <input type="text" id="education" name="education" value="{ed_val}" placeholder="School, bootcamp, YouTube, the streets...">
                    <label for="photo_url">Profile photo URL</label>
                    <input type="text" id="photo_url" name="photo_url" value="{pu_val}" placeholder="https://...">
                    <label for="looking_for">Looking for (comma-separated)</label>
                    <input type="text" id="looking_for" name="looking_for" value="{lf_val}">
                    <label for="interests">Interests (comma-separated)</label>
                    <input type="text" id="interests" name="interests" value="{int_val}">
                    <button type="submit">Save profile</button>
                </form>
            </div>"""

    elif section == "browse":
        if not browse_profiles:
            main_content = '<div class="empty-state"><p>No profiles yet. Be the first &mdash; <a href="/surge">join Surge</a>.</p></div>'
        else:
            for p in browse_profiles:
                initial = html_escape(p.name[0].upper()) if p.name else "?"
                tags = ""
                if p.looking_for:
                    tags = "".join(
                        f'<span class="tag">{html_escape(t.strip())}</span>'
                        for t in p.looking_for.split(",") if t.strip()
                    )
                main_content += f'''
                <div class="feed-item">
                    <div class="feed-avatar">{initial}</div>
                    <div class="feed-body">
                        <div class="feed-meta">
                            <strong>{html_escape(p.name)}</strong>
                        </div>
                        <div class="feed-text">{html_escape(p.bio or "")}</div>
                        <div class="feed-tags">{tags}</div>
                    </div>
                </div>'''

    # Section title for the sticky header
    section_titles = {"inbox": "Inbox", "conversations": "Conversations", "profile": "Profile", "browse": "Browse"}
    section_title = section_titles.get(section, "BotJoin")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>BotJoin</title>
    <meta http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #fff;
            color: #0f1419;
            height: 100vh;
        }}

        /* X-style 3-column layout */
        .shell {{
            display: flex;
            max-width: 1280px;
            margin: 0 auto;
            height: 100vh;
        }}

        /* Left sidebar — sticky nav */
        .sidebar {{
            width: 275px;
            flex-shrink: 0;
            height: 100vh;
            position: sticky;
            top: 0;
            display: flex;
            flex-direction: column;
            padding: 12px 12px 20px;
            border-right: 1px solid #eff3f4;
        }}
        .sidebar-brand {{
            display: block;
            padding: 12px 16px;
            font-size: 24px;
            font-weight: 800;
            color: #0f1419;
            text-decoration: none;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }}
        .sidebar-brand:hover {{ color: #1d9bf0; }}

        /* Nav items — big, bold, X-style */
        .nav-item {{
            display: flex;
            align-items: center;
            gap: 20px;
            padding: 12px 16px;
            font-size: 20px;
            color: #0f1419;
            text-decoration: none;
            border-radius: 9999px;
            transition: background 0.2s;
        }}
        .nav-item:hover {{ background: rgba(15,20,25,0.1); }}
        .nav-item.active {{ font-weight: 700; }}
        .nav-icon {{ font-size: 22px; width: 26px; text-align: center; }}
        .nav-label {{ white-space: nowrap; }}
        .nav-badge {{
            background: #1d9bf0;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            padding: 1px 8px;
            border-radius: 9999px;
            margin-left: auto;
        }}

        /* Connection items */
        .nav-divider {{ height: 1px; background: #eff3f4; margin: 8px 16px; }}
        .conn-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            font-size: 14px;
            color: #536471;
            text-decoration: none;
            border-radius: 9999px;
            transition: background 0.2s;
        }}
        .conn-item:hover {{ background: rgba(15,20,25,0.1); color: #0f1419; }}
        .conn-dot {{
            width: 8px; height: 8px;
            background: #00ba7c;
            border-radius: 50%;
            flex-shrink: 0;
        }}

        .sidebar-cta {{
            display: block;
            padding: 8px 16px;
            font-size: 15px;
            font-weight: 500;
            color: #1d9bf0;
            text-decoration: none;
            border-radius: 9999px;
            transition: background 0.2s;
        }}
        .sidebar-cta:hover {{ background: rgba(29,155,240,0.1); }}
        .sidebar-bottom {{ margin-top: auto; }}

        /* User card at bottom of sidebar */
        .user-card {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 9999px;
            transition: background 0.2s;
            cursor: default;
        }}
        .user-card:hover {{ background: rgba(15,20,25,0.1); }}
        .user-card-avatar {{
            width: 40px; height: 40px;
            border-radius: 50%;
            background: #cfd9de;
            color: #0f1419;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            flex-shrink: 0;
        }}
        .user-card-info {{ flex: 1; min-width: 0; }}
        .user-card-name {{ font-size: 15px; font-weight: 700; color: #0f1419; }}
        .user-card-email {{ font-size: 13px; color: #536471; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .user-card-logout {{
            font-size: 13px;
            color: #536471;
            text-decoration: none;
            padding: 4px 12px;
            border-radius: 9999px;
            transition: all 0.2s;
        }}
        .user-card-logout:hover {{ color: #f4212e; background: rgba(244,33,46,0.1); }}

        /* Main feed column */
        .main {{
            flex: 1;
            max-width: 600px;
            border-right: 1px solid #eff3f4;
            overflow-y: auto;
            height: 100vh;
        }}

        /* Sticky section header */
        .feed-header {{
            position: sticky;
            top: 0;
            background: rgba(255,255,255,0.85);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            padding: 12px 16px;
            font-size: 20px;
            font-weight: 700;
            color: #0f1419;
            border-bottom: 1px solid #eff3f4;
            z-index: 10;
        }}

        /* Feed items — X-style posts */
        .feed-item {{
            display: flex;
            gap: 12px;
            padding: 12px 16px;
            border-bottom: 1px solid #eff3f4;
            transition: background 0.2s;
        }}
        .feed-item:hover {{ background: rgba(0,0,0,0.03); }}
        .feed-unread {{ background: rgba(29,155,240,0.04); }}
        .feed-avatar {{
            width: 40px; height: 40px;
            border-radius: 50%;
            background: #cfd9de;
            color: #0f1419;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            flex-shrink: 0;
        }}
        .feed-body {{ flex: 1; min-width: 0; }}
        .feed-meta {{
            display: flex;
            align-items: baseline;
            gap: 4px;
            flex-wrap: wrap;
        }}
        .feed-meta strong {{ font-size: 15px; color: #0f1419; }}
        .feed-secondary {{ font-size: 15px; color: #536471; }}
        .feed-dot {{ color: #536471; font-size: 15px; }}
        .feed-time {{ font-size: 15px; color: #536471; }}
        .feed-text {{
            font-size: 15px;
            line-height: 1.5;
            color: #0f1419;
            white-space: pre-wrap;
            word-break: break-word;
            margin-top: 4px;
        }}
        .feed-tags {{
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .tag {{
            font-size: 13px;
            color: #1d9bf0;
            background: rgba(29,155,240,0.1);
            padding: 2px 10px;
            border-radius: 9999px;
        }}

        /* Reply row */
        .reply-row {{
            display: flex;
            gap: 8px;
            margin-top: 12px;
        }}
        .reply-row input {{
            flex: 1;
            padding: 8px 14px;
            background: #fff;
            border: 1px solid #cfd9de;
            border-radius: 9999px;
            font-size: 15px;
            color: #0f1419;
            font-family: inherit;
        }}
        .reply-row input::placeholder {{ color: #536471; }}
        .reply-row input:focus {{
            outline: none;
            border-color: #1d9bf0;
        }}
        .reply-row button {{
            padding: 8px 20px;
            background: #1d9bf0;
            color: #fff;
            border: none;
            border-radius: 9999px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .reply-row button:hover {{ background: #1a8cd8; }}

        /* Empty state */
        .empty-state {{
            text-align: center;
            padding: 60px 20px;
        }}
        .empty-state h3 {{
            font-size: 20px;
            font-weight: 800;
            color: #0f1419;
            margin-bottom: 8px;
        }}
        .empty-state p {{
            font-size: 15px;
            color: #536471;
            line-height: 1.5;
        }}
        .empty-state a {{ color: #1d9bf0; text-decoration: none; }}
        .action-btn {{
            display: inline-block;
            margin-top: 20px;
            padding: 12px 28px;
            background: #1d9bf0;
            color: #fff;
            border-radius: 9999px;
            font-size: 15px;
            font-weight: 700;
            text-decoration: none;
            transition: background 0.2s;
        }}
        .action-btn:hover {{ background: #1a8cd8; }}

        /* Profile section */
        .profile-card {{
            padding: 20px 16px;
            border-bottom: 1px solid #eff3f4;
        }}
        .profile-name {{ font-size: 20px; font-weight: 800; color: #0f1419; }}
        .profile-email {{ font-size: 15px; color: #536471; margin-bottom: 16px; }}
        .profile-form label {{
            display: block;
            font-size: 13px;
            font-weight: 700;
            color: #536471;
            margin: 16px 0 6px;
        }}
        .profile-form textarea, .profile-form input[type="text"] {{
            width: 100%;
            padding: 12px 14px;
            background: #f7f9f9;
            border: 1px solid #cfd9de;
            border-radius: 4px;
            font-size: 15px;
            font-family: inherit;
            color: #0f1419;
            resize: vertical;
        }}
        .profile-form textarea:focus, .profile-form input:focus {{
            outline: none;
            border-color: #1d9bf0;
            background: #fff;
        }}
        .profile-form button {{
            margin-top: 16px;
            padding: 10px 24px;
            background: #0f1419;
            color: #fff;
            border: none;
            border-radius: 9999px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .profile-form button:hover {{ background: #272c30; }}

        /* Conversations */
        .connection-group {{ border-bottom: 1px solid #eff3f4; }}
        .connection-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 15px;
            font-weight: 700;
            padding: 16px;
            color: #0f1419;
        }}
        .conn-avatar {{
            display: inline-flex;
            width: 24px; height: 24px;
            border-radius: 50%;
            background: #cfd9de;
            color: #0f1419;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 11px;
        }}
        .contract-badge {{
            font-size: 13px;
            color: #536471;
            font-weight: 400;
        }}
        .thread {{
            padding: 0 16px 16px;
        }}
        .thread-header {{
            font-weight: 700;
            font-size: 13px;
            color: #536471;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #eff3f4;
        }}
        .msg {{
            padding: 10px 14px;
            margin-bottom: 8px;
            border-radius: 16px;
            font-size: 15px;
            max-width: 80%;
        }}
        .msg-mine {{
            background: #1d9bf0;
            color: #fff;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }}
        .msg-theirs {{
            background: #eff3f4;
            color: #0f1419;
            margin-right: auto;
            border-bottom-left-radius: 4px;
        }}
        .msg-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
        }}
        .msg-sender {{ font-size: 13px; font-weight: 700; color: inherit; opacity: 0.7; }}
        .msg-time {{ font-size: 13px; color: inherit; opacity: 0.5; }}
        .msg-content {{
            line-height: 1.4;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .msg-meta {{ font-size: 12px; opacity: 0.5; margin-top: 4px; }}

        /* Setup guide */
        .setup-guide {{ padding: 32px 16px; }}
        .setup-guide h2 {{ font-size: 24px; font-weight: 800; margin-bottom: 8px; color: #0f1419; }}
        .setup-subtitle {{ font-size: 15px; color: #536471; margin-bottom: 28px; }}
        .setup-steps {{ display: flex; flex-direction: column; gap: 16px; margin-bottom: 28px; }}
        .setup-step {{
            display: flex; gap: 16px;
            border: 1px solid #eff3f4;
            border-radius: 16px; padding: 16px;
        }}
        .setup-step-num {{
            display: flex; align-items: center; justify-content: center;
            min-width: 28px; height: 28px;
            background: #0f1419; color: #fff;
            border-radius: 50%; font-size: 14px; font-weight: 700;
        }}
        .setup-step h3 {{ font-size: 15px; font-weight: 700; margin: 0 0 4px; color: #0f1419; }}
        .setup-step p {{ font-size: 15px; color: #536471; margin: 0 0 8px; line-height: 1.4; }}
        .setup-code {{
            display: block;
            background: #f7f9f9; border: 1px solid #eff3f4;
            border-radius: 4px; padding: 8px 12px;
            font-family: 'SF Mono', 'Menlo', monospace;
            font-size: 13px; color: #0f1419; margin-top: 8px;
            overflow-x: auto; white-space: nowrap;
        }}
        .setup-links {{ display: flex; gap: 12px; flex-wrap: wrap; }}
        .setup-btn {{
            display: inline-block; padding: 10px 24px;
            border-radius: 9999px; font-size: 15px; font-weight: 700;
            text-decoration: none; background: #0f1419; color: #fff;
            transition: background 0.2s;
        }}
        .setup-btn:hover {{ background: #272c30; }}
        .setup-btn-secondary {{
            background: #fff; color: #0f1419;
            border: 1px solid #cfd9de;
        }}
        .setup-btn-secondary:hover {{ background: #f7f9f9; }}
        .setup-tabs {{
            display: flex; border-bottom: 1px solid #eff3f4;
            margin-top: 12px;
        }}
        .setup-tab {{
            padding: 12px 16px; border: none; background: none;
            font-size: 15px; font-weight: 500; color: #536471;
            cursor: pointer; border-bottom: 2px solid transparent;
            margin-bottom: -1px; transition: color 0.2s;
        }}
        .setup-tab:hover {{ color: #0f1419; background: rgba(15,20,25,0.1); }}
        .setup-tab.active {{ color: #0f1419; font-weight: 700; border-bottom-color: #1d9bf0; }}
        .setup-tab-content {{ display: none; padding: 16px 0 0; }}
        .setup-tab-content.active {{ display: block; }}
        .setup-tab-content p {{ font-size: 15px; color: #536471; margin: 0 0 8px; }}

        /* Section header (used in profile, etc.) */
        .section-header {{
            padding: 20px 16px 0;
        }}
        .section-header h2 {{
            font-size: 20px;
            font-weight: 800;
            color: #0f1419;
        }}

        /* Right panel */
        .right-panel {{
            width: 350px;
            flex-shrink: 0;
            padding: 12px 24px;
        }}
        .right-box {{
            background: #f7f9f9;
            border-radius: 16px;
            margin-bottom: 16px;
            overflow: hidden;
        }}
        .right-box-title {{
            font-size: 20px;
            font-weight: 800;
            color: #0f1419;
            padding: 12px 16px;
        }}
        .right-box-item {{
            display: block;
            padding: 12px 16px;
            border-top: 1px solid #eff3f4;
            text-decoration: none;
            transition: background 0.2s;
        }}
        .right-box-item:hover {{ background: rgba(0,0,0,0.03); }}
        .right-box-label {{
            font-size: 13px;
            color: #536471;
        }}
        .right-box-text {{
            font-size: 15px;
            font-weight: 700;
            color: #0f1419;
            margin-top: 2px;
        }}
        .right-box-sub {{
            font-size: 13px;
            color: #536471;
            margin-top: 2px;
        }}
        .right-box-footer {{
            display: block;
            padding: 16px;
            border-top: 1px solid #eff3f4;
            color: #1d9bf0;
            font-size: 15px;
            text-decoration: none;
            transition: background 0.2s;
        }}
        .right-box-footer:hover {{ background: rgba(0,0,0,0.03); }}
        .right-search {{
            width: 100%;
            padding: 12px 16px;
            background: #eff3f4;
            border: 1px solid transparent;
            border-radius: 9999px;
            font-size: 15px;
            font-family: inherit;
            color: #0f1419;
            margin-bottom: 16px;
        }}
        .right-search::placeholder {{ color: #536471; }}
        .right-search:focus {{
            outline: none;
            border-color: #1d9bf0;
            background: #fff;
        }}

        @media (max-width: 1024px) {{
            .right-panel {{ display: none; }}
        }}
        @media (max-width: 768px) {{
            .sidebar {{ width: 72px; padding: 12px 4px 20px; }}
            .nav-label, .sidebar-brand, .user-card-info, .user-card-logout, .sidebar-cta, .conn-item {{ display: none; }}
            .nav-item {{ justify-content: center; padding: 12px; }}
            .sidebar-brand {{ display: none; }}
        }}
        @media (max-width: 500px) {{
            .sidebar {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="shell">
        <nav class="sidebar">
            <a href="/" class="sidebar-brand">BotJoin</a>
            {nav_html}
            {conn_list}
            <div class="sidebar-bottom">
                {cta_html}
                <div class="user-card">
                    <div class="user-card-avatar">{html_escape(user.name[0].upper())}</div>
                    <div class="user-card-info">
                        <div class="user-card-name">{html_escape(user.name)}</div>
                        <div class="user-card-email">{html_escape(user.email)}</div>
                    </div>
                    <a href="/observe/logout" class="user-card-logout">Logout</a>
                </div>
            </div>
        </nav>

        <main class="main">
            <div class="feed-header">{section_title}</div>
            {main_content}
        </main>

        <aside class="right-panel">
            {_right_panel_html(section, has_agents, is_surge_user, connection_infos, browse_profiles)}
        </aside>
    </div>

    <script>
    function switchTab(event, tabId) {{
        document.querySelectorAll('.setup-tab').forEach(function(t) {{ t.classList.remove('active'); }});
        document.querySelectorAll('.setup-tab-content').forEach(function(c) {{ c.classList.remove('active'); }});
        event.target.classList.add('active');
        document.getElementById(tabId).classList.add('active');
    }}
    </script>
</body>
</html>"""

    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Dashboard actions (POST)
# ---------------------------------------------------------------------------


@router.post("/observe/outreach/{outreach_id}/reply", response_class=HTMLResponse)
async def observe_outreach_reply(
    outreach_id: str,
    content: str = Form(...),
    botjoin_jwt: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Reply to an outreach message from the dashboard inbox.
    Creates an OutreachReply row that the sending agent can poll for.
    """
    if not botjoin_jwt:
        return RedirectResponse(url="/observe", status_code=303)

    try:
        user = await _get_user_by_jwt(botjoin_jwt, db)
    except HTTPException:
        return RedirectResponse(url="/observe", status_code=303)

    # Find the outreach
    result = await db.execute(
        select(Outreach).where(Outreach.id == outreach_id, Outreach.to_user_id == user.id)
    )
    outreach = result.scalar_one_or_none()
    if not outreach:
        return RedirectResponse(url="/observe?section=inbox", status_code=303)

    # Create the reply
    reply = OutreachReply(
        outreach_id=outreach.id,
        from_user_id=user.id,
        content=content,
    )
    db.add(reply)

    # Update outreach status
    outreach.status = "replied"
    await db.commit()

    return RedirectResponse(url="/observe?section=inbox", status_code=303)


@router.post("/observe/profile", response_class=HTMLResponse)
async def observe_profile_update(
    bio: str = Form(""),
    looking_for: str = Form(""),
    interests: str = Form(""),
    superpower: str = Form(""),
    current_project: str = Form(""),
    need_help_with: str = Form(""),
    dream_collab: str = Form(""),
    fun_fact: str = Form(""),
    education: str = Form(""),
    photo_url: str = Form(""),
    botjoin_jwt: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Update the user's Surge profile from the dashboard."""
    if not botjoin_jwt:
        return RedirectResponse(url="/observe", status_code=303)

    try:
        user = await _get_user_by_jwt(botjoin_jwt, db)
    except HTTPException:
        return RedirectResponse(url="/observe", status_code=303)

    user.bio = bio
    user.looking_for = looking_for
    user.interests = interests
    user.superpower = superpower
    user.current_project = current_project
    user.need_help_with = need_help_with
    user.dream_collab = dream_collab
    user.fun_fact = fun_fact
    user.education = education
    user.photo_url = photo_url
    await db.commit()

    return RedirectResponse(url="/observe?section=profile", status_code=303)
