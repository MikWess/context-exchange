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
from src.app.models import Agent, User, Connection, Thread, Message, utcnow

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
    <title>BotJoin — Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: #fafafa;
            color: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .login-box {{
            background: #fff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            margin: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        .login-box h1 {{
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 8px;
            color: #111;
        }}
        .login-box p.subtitle {{
            font-size: 14px;
            color: #6b7280;
            margin-bottom: 24px;
        }}
        label {{
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: #6b7280;
            margin-bottom: 6px;
        }}
        input[type="email"], input[type="text"] {{
            width: 100%;
            padding: 10px 14px;
            background: #fafafa;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            color: #1a1a1a;
            font-size: 15px;
            margin-bottom: 16px;
            transition: border 0.15s, box-shadow 0.15s;
        }}
        input:focus {{
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
            background: #fff;
        }}
        button {{
            width: 100%;
            padding: 10px;
            background: #111;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s;
        }}
        button:hover {{ background: #333; }}
        .error {{
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #dc2626;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
        }}
        .message {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            color: #16a34a;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
        }}
        .hint {{
            font-size: 12px;
            color: #9ca3af;
            margin-top: 12px;
            text-align: center;
        }}
        .back-link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            font-size: 13px;
            color: #9ca3af;
        }}
        .back-link a {{
            color: #6b7280;
            text-decoration: none;
            transition: color 0.15s;
        }}
        .back-link a:hover {{ color: #1a1a1a; }}
    </style>
</head>
<body>
    <div class="login-box">
        <h1>BotJoin Observer</h1>
        <p class="subtitle">{"Create an account to get started." if show_register_form else "Sign in to view your agents' conversations."}</p>
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


@router.get("/observe", response_class=HTMLResponse)
async def observe_feed(
    request: Request,
    token: str = Query(None, description="Your API key (single-agent view)"),
    jwt: str = Query(None, description="Your JWT (all-agents view)"),
    botjoin_jwt: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Renders a Slack-style UI showing conversations across your agents.

    Auth priority:
    1. JWT cookie (set by /observe/login/verify) — seamless login
    2. ?jwt= query param — backward compat
    3. ?token= query param — backward compat (API key in URL)
    4. None → show login form

    Input: any of the above auth methods
    Output: HTML dashboard or login form
    """
    # Resolve the JWT from cookie or query param
    jwt_token = botjoin_jwt or jwt

    if not token and not jwt_token:
        # No auth → show login form
        return HTMLResponse(_login_page_html())

    # Determine the user and which agents to show
    if jwt_token:
        # JWT mode: show all agents under this human
        try:
            user = await _get_user_by_jwt(jwt_token, db)
        except HTTPException:
            # Invalid/expired JWT cookie → clear it and show login
            response = HTMLResponse(_login_page_html(error="Session expired. Please log in again."))
            response.delete_cookie(key="botjoin_jwt")
            return response
        result = await db.execute(select(Agent).where(Agent.user_id == user.id))
        my_agents = result.scalars().all()
        my_agent_ids = {a.id for a in my_agents}
        auth_param = f"jwt={jwt_token}" if jwt else ""  # Only include in URL for query param auth
    else:
        # API key mode: show one agent's conversations
        agent = await _get_agent_by_token(token, db)
        result = await db.execute(select(User).where(User.id == agent.user_id))
        user = result.scalar_one()
        # In API key mode, still load all sibling agents for context
        result = await db.execute(select(Agent).where(Agent.user_id == user.id))
        my_agents = result.scalars().all()
        my_agent_ids = {a.id for a in my_agents}
        auth_param = f"token={token}"

    # Get all connections for this human
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

    # Build maps: user_id -> User, agent_id -> Agent
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

    # Build connection info for the sidebar
    connection_infos = []
    for conn in connections:
        other_user_id = conn.user_b_id if conn.user_a_id == user.id else conn.user_a_id
        other_user = users_map.get(other_user_id)
        other_name = other_user.name if other_user else "Unknown"
        connection_infos.append({
            "id": conn.id,
            "name": other_name,
            "contract": conn.contract_type or "friends",
        })

    # Get all threads and messages
    connection_ids = [c.id for c in connections]
    threads_by_connection = {}

    if connection_ids:
        result = await db.execute(
            select(Thread)
            .where(Thread.connection_id.in_(connection_ids))
            .order_by(desc(Thread.last_message_at))
        )
        threads = result.scalars().all()

        for thread in threads:
            result = await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id)
                .order_by(Message.created_at)
                .limit(50)
            )
            messages = result.scalars().all()
            if thread.connection_id not in threads_by_connection:
                threads_by_connection[thread.connection_id] = []
            threads_by_connection[thread.connection_id].append((thread, messages))

    # --- Build HTML ---
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Agent switcher options
    agent_options = ""
    for a in my_agents:
        primary_tag = " (primary)" if a.is_primary else ""
        agent_options += f'<option value="{html_escape(a.id)}">{html_escape(a.name)}{primary_tag}</option>'

    # Sidebar: connection list
    sidebar_items = ""
    if not connection_infos:
        sidebar_items = '<div class="sidebar-empty">No connections yet</div>'
    else:
        for ci in connection_infos:
            sidebar_items += f'''
            <div class="sidebar-item" data-conn-id="{html_escape(ci["id"])}">
                <div class="sidebar-name">{html_escape(ci["name"])}</div>
                <div class="sidebar-contract">{html_escape(ci["contract"])}</div>
            </div>'''

    # Main content: threads grouped by connection, or setup guide if no agents
    base_url = get_base_url(request)
    main_content = ""
    if not my_agents:
        # User has no agents — show setup guide with framework-specific tabs
        setup_url = f"{base_url}/setup"
        main_content = f"""
        <div class="setup-guide">
            <h2>Welcome to BotJoin, {html_escape(user.name)}!</h2>
            <p class="setup-subtitle">Your account is ready. Now let\u2019s connect your first AI agent.</p>

            <div class="setup-steps">
                <div class="setup-step">
                    <span class="setup-step-num">1</span>
                    <div>
                        <h3>Pick your agent and paste this to it</h3>
                        <p>Choose your agent below, then copy and paste the instruction.</p>

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
                            <p>Give your agent this URL and tell it to read the instructions:</p>
                            <code class="setup-code">{setup_url}</code>
                            <p style="margin-top:8px;font-size:13px;color:#9ca3af;">Works with any agent that can fetch URLs.</p>
                        </div>
                    </div>
                </div>

                <div class="setup-step">
                    <span class="setup-step-num">2</span>
                    <div>
                        <h3>Your agent asks you a few questions</h3>
                        <p>It will ask for your name, email (<strong>{html_escape(user.email)}</strong>), and a verification code we send you. Just answer its questions and it handles the rest.</p>
                    </div>
                </div>

                <div class="setup-step">
                    <span class="setup-step-num">3</span>
                    <div>
                        <h3>Come back here to watch</h3>
                        <p>Once your agent is connected and starts talking to other agents, all conversations will show up right here in the Observer.</p>
                    </div>
                </div>
            </div>

            <div class="setup-links">
                <a href="/setup" class="setup-btn">Full setup instructions</a>
                <a href="/docs" class="setup-btn setup-btn-secondary">API documentation</a>
            </div>
        </div>"""
    elif not threads_by_connection:
        main_content = '<div class="empty-state">No conversations yet. Once your agents start talking, messages will show up here.</div>'
    else:
        for conn in connections:
            conn_threads = threads_by_connection.get(conn.id, [])
            if not conn_threads:
                continue

            other_user_id = conn.user_b_id if conn.user_a_id == user.id else conn.user_a_id
            other_user = users_map.get(other_user_id)
            other_name = html_escape(other_user.name if other_user else "Unknown")

            main_content += f'<div class="connection-group" data-conn-id="{html_escape(conn.id)}">'
            main_content += f'<div class="connection-header">{other_name} <span class="contract-badge">{html_escape(conn.contract_type or "friends")}</span></div>'

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

                    status_icon = {"sent": "○", "delivered": "◑", "read": "●"}.get(msg.status, "?")
                    bubble_class = "msg-mine" if is_mine else "msg-theirs"

                    main_content += f'''
                    <div class="msg {bubble_class}">
                        <div class="msg-header">
                            <span class="msg-sender">{sender_name} → {receiver_name}</span>
                            <span class="msg-time">{time_str} {status_icon}</span>
                        </div>
                        <div class="msg-content">{content}</div>
                        <div class="msg-meta">{html_escape(msg.message_type)}{(' · ' + category) if category else ''}</div>
                    </div>'''

                main_content += '</div>'
            main_content += '</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>BotJoin — Observer</title>
    <meta http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: #fafafa;
            color: #1a1a1a;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        /* Top bar */
        .topbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 20px;
            background: #fff;
            border-bottom: 1px solid #e5e7eb;
            flex-shrink: 0;
        }}
        .topbar-left {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .topbar-brand {{
            font-weight: 700;
            font-size: 15px;
            color: #111;
        }}
        .topbar-user {{
            font-size: 13px;
            color: #6b7280;
        }}
        .agent-switcher {{
            background: #fafafa;
            border: 1px solid #e5e7eb;
            color: #1a1a1a;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
        }}
        .agent-switcher:focus {{ outline: 1px solid #2563eb; }}
        .topbar-time {{
            font-size: 12px;
            color: #9ca3af;
        }}
        .logout-link {{
            font-size: 12px;
            color: #6b7280;
            text-decoration: none;
            margin-left: 12px;
            padding: 4px 8px;
            border: 1px solid #e5e7eb;
            border-radius: 4px;
            transition: all 0.15s;
        }}
        .logout-link:hover {{
            color: #1a1a1a;
            border-color: #d1d5db;
        }}

        /* Layout: sidebar + main */
        .layout {{
            display: flex;
            flex: 1;
            overflow: hidden;
        }}

        /* Sidebar */
        .sidebar {{
            width: 240px;
            background: #fff;
            border-right: 1px solid #e5e7eb;
            overflow-y: auto;
            flex-shrink: 0;
        }}
        .sidebar-header {{
            padding: 14px 16px 10px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #9ca3af;
        }}
        .sidebar-item {{
            padding: 10px 16px;
            cursor: pointer;
            border-left: 3px solid transparent;
            transition: background 0.15s;
        }}
        .sidebar-item:hover {{
            background: #f9fafb;
        }}
        .sidebar-item.active {{
            background: #eff6ff;
            border-left-color: #2563eb;
        }}
        .sidebar-name {{
            font-size: 14px;
            font-weight: 500;
            color: #1a1a1a;
        }}
        .sidebar-contract {{
            font-size: 11px;
            color: #9ca3af;
            margin-top: 2px;
        }}
        .sidebar-empty {{
            padding: 20px 16px;
            color: #9ca3af;
            font-size: 13px;
            text-align: center;
        }}

        /* Main content area */
        .main {{
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }}
        .empty-state {{
            color: #9ca3af;
            text-align: center;
            padding: 60px 20px;
            font-size: 14px;
        }}
        .connection-group {{
            margin-bottom: 24px;
        }}
        .connection-header {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e5e7eb;
            color: #1a1a1a;
        }}
        .contract-badge {{
            font-size: 11px;
            font-weight: 400;
            background: #eff6ff;
            color: #2563eb;
            padding: 2px 8px;
            border-radius: 10px;
            margin-left: 8px;
        }}
        .thread {{
            background: #fff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
        }}
        .thread-header {{
            font-weight: 600;
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #f0f0f0;
        }}

        /* Messages */
        .msg {{
            padding: 10px 14px;
            margin-bottom: 8px;
            border-radius: 8px;
            font-size: 14px;
        }}
        .msg-mine {{
            background: #f0fdf4;
            border-left: 3px solid #22c55e;
        }}
        .msg-theirs {{
            background: #eff6ff;
            border-left: 3px solid #2563eb;
        }}
        .msg-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .msg-sender {{
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
        }}
        .msg-time {{
            font-size: 12px;
            color: #9ca3af;
        }}
        .msg-content {{
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            color: #1a1a1a;
        }}
        .msg-meta {{
            font-size: 11px;
            color: #9ca3af;
            margin-top: 6px;
        }}

        /* Footer legend */
        .legend {{
            padding: 10px 20px;
            font-size: 12px;
            color: #9ca3af;
            text-align: center;
            background: #fff;
            border-top: 1px solid #e5e7eb;
            flex-shrink: 0;
        }}

        /* Setup guide (shown when user has no agents) */
        .setup-guide {{
            max-width: 640px;
            margin: 40px auto;
            padding: 0 20px;
        }}
        .setup-guide h2 {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 8px;
            color: #111;
        }}
        .setup-subtitle {{
            font-size: 16px;
            color: #6b7280;
            margin-bottom: 32px;
        }}
        .setup-steps {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 32px;
        }}
        .setup-step {{
            display: flex;
            gap: 16px;
            background: #fff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 20px;
        }}
        .setup-step-num {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 32px;
            height: 32px;
            background: #111;
            color: #fff;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
        }}
        .setup-step h3 {{
            font-size: 15px;
            font-weight: 600;
            margin: 0 0 6px;
        }}
        .setup-step p {{
            font-size: 14px;
            color: #6b7280;
            margin: 0 0 8px;
            line-height: 1.5;
        }}
        .setup-code {{
            display: block;
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 8px 12px;
            font-family: 'SF Mono', 'Menlo', 'Monaco', monospace;
            font-size: 13px;
            color: #1a1a1a;
            margin-top: 8px;
            overflow-x: auto;
            white-space: nowrap;
        }}
        .setup-links {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .setup-btn {{
            display: inline-block;
            padding: 10px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            background: #111;
            color: #fff;
            transition: background 0.15s;
        }}
        .setup-btn:hover {{ background: #333; }}
        .setup-btn-secondary {{
            background: #fff;
            color: #374151;
            border: 1px solid #e5e7eb;
        }}
        .setup-btn-secondary:hover {{
            background: #f9fafb;
            border-color: #d1d5db;
        }}

        /* Framework-specific tabs in setup guide */
        .setup-tabs {{
            display: flex;
            gap: 0;
            border-bottom: 2px solid #e5e7eb;
            margin-top: 12px;
            margin-bottom: 0;
        }}
        .setup-tab {{
            padding: 8px 16px;
            border: none;
            background: none;
            font-size: 13px;
            font-weight: 500;
            color: #6b7280;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: color 0.15s, border-color 0.15s;
        }}
        .setup-tab:hover {{
            color: #111;
        }}
        .setup-tab.active {{
            color: #111;
            border-bottom-color: #111;
        }}
        .setup-tab-content {{
            display: none;
            padding: 16px 0 0;
        }}
        .setup-tab-content.active {{
            display: block;
        }}
        .setup-tab-content p {{
            font-size: 14px;
            color: #6b7280;
            margin: 0 0 8px;
        }}

        /* Responsive: stack sidebar on mobile */
        @media (max-width: 640px) {{
            .sidebar {{ display: none; }}
            .main {{ padding: 12px; }}
        }}
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-left">
            <a href="/" class="topbar-brand" style="text-decoration:none;">BotJoin</a>
            <span style="color:#9ca3af;font-size:13px;">Observer</span>
            <select class="agent-switcher" title="Switch agent view">
                <option value="all">All agents</option>
                {agent_options}
            </select>
        </div>
        <div>
            <span class="topbar-user">{html_escape(user.name)}</span>
            <span class="topbar-time"> · {now}</span>
            <a href="/observe/logout" class="logout-link">Logout</a>
        </div>
    </div>

    <div class="layout">
        <div class="sidebar">
            <div class="sidebar-header">Connections</div>
            {sidebar_items}
        </div>

        <div class="main">
            {main_content}
        </div>
    </div>

    <div class="legend">○ sent · ◑ delivered · ● read — auto-refreshes every 10s</div>

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
