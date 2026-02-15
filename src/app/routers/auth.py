"""
Auth router — registration and login.

POST /auth/register  → Create a user + agent, return API key (agent calls this)
POST /auth/login     → Get a JWT for the dashboard (human calls this)
GET  /auth/me        → Get current agent's profile (agent calls this)
PUT  /auth/me        → Update agent settings (webhook_url, etc.)
"""
import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import (
    generate_api_key,
    hash_api_key,
    create_jwt_token,
    get_current_agent,
)
from src.app.database import get_db
from src.app.models import User, Agent
from src.app.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    AgentProfile,
    AgentUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _validate_webhook_url(url: str):
    """
    Validate a webhook URL to prevent SSRF attacks.

    Rules:
    - Must be HTTPS (no http, no ftp, no file://, etc.)
    - Hostname must not resolve to a private/internal IP
    - Blocks localhost, 127.x.x.x, 10.x.x.x, 172.16-31.x.x, 192.168.x.x,
      169.254.x.x (link-local/AWS metadata), and IPv6 loopback
    """
    parsed = urlparse(url)

    # Must be HTTPS
    if parsed.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="Webhook URL must use HTTPS",
        )

    # Must have a hostname
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=400,
            detail="Webhook URL must include a hostname",
        )

    # Block obviously private hostnames
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise HTTPException(
            status_code=400,
            detail="Webhook URL cannot point to localhost",
        )

    # Try to parse as IP address and block private ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(
                status_code=400,
                detail="Webhook URL cannot point to a private or reserved IP address",
            )
    except ValueError:
        # Not an IP literal — it's a hostname, which is fine
        # (DNS resolution to private IPs is a deeper issue for later)
        pass


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user + agent.

    Input: email, name, agent_name, optional framework
    Output: user_id, agent_id, and the API key (shown ONCE)

    The agent calls this during the setup flow. The API key is returned
    in plaintext exactly once — the agent must store it. We only keep
    the hash.
    """
    # Check if email already registered
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Create user
    user = User(email=req.email, name=req.name)
    db.add(user)
    await db.flush()  # get the user.id

    # Generate API key and hash it
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    # Validate webhook URL if provided (SSRF protection)
    if req.webhook_url:
        _validate_webhook_url(req.webhook_url)

    # Create agent linked to user
    agent = Agent(
        user_id=user.id,
        name=req.agent_name,
        api_key_hash=key_hash,
        framework=req.framework,
        webhook_url=req.webhook_url,
    )
    db.add(agent)
    await db.flush()

    return RegisterResponse(
        user_id=user.id,
        agent_id=agent.id,
        api_key=raw_key,
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login for the dashboard.

    Input: email
    Output: JWT token

    MVP: email-only login (no password). Good enough for dev.
    Will add OAuth (Google) for production.
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email. Register through your agent first.",
        )

    token = create_jwt_token(user.id)
    return LoginResponse(token=token, user_id=user.id, name=user.name)


@router.get("/me", response_model=AgentProfile)
async def get_me(agent: Agent = Depends(get_current_agent)):
    """
    Get the current agent's profile.

    Input: API key (in Authorization header)
    Output: Agent profile with id, name, framework, status, webhook_url, etc.

    Agents call this to verify their API key works and see their own info.
    """
    return AgentProfile.model_validate(agent)


@router.put("/me", response_model=AgentProfile)
async def update_me(
    req: AgentUpdateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Update agent settings.

    Input: API key + fields to update (currently just webhook_url)
    Output: Updated agent profile

    Set webhook_url to receive instant notifications when messages arrive.
    Set to empty string or null to clear it (fall back to polling).
    """
    if req.webhook_url is not None:
        if req.webhook_url:
            # Validate before saving (SSRF protection)
            _validate_webhook_url(req.webhook_url)
            agent.webhook_url = req.webhook_url
        else:
            # Empty string means "clear my webhook"
            agent.webhook_url = None

    return AgentProfile.model_validate(agent)
