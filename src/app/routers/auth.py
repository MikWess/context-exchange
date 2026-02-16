"""
Auth router — registration, verification, login, and multi-agent management.

POST /auth/register  → Start registration: send verification code to email
POST /auth/verify    → Complete registration: verify code, create agent, return API key
POST /auth/login     → Get a JWT for the dashboard (human calls this)
GET  /auth/me        → Get current agent's profile (agent calls this)
PUT  /auth/me        → Update agent settings (webhook_url, etc.)
POST /auth/agents    → Add another agent to your account (authenticated)
GET  /auth/agents    → List all agents under your account
"""
import ipaddress
from datetime import timedelta
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
from src.app.config import EMAIL_VERIFICATION_EXPIRE_MINUTES, RESEND_API_KEY
from src.app.database import get_db
from src.app.email import generate_verification_code, send_verification_email
from src.app.models import User, Agent, utcnow
from src.app.schemas import (
    RegisterRequest,
    RegisterPendingResponse,
    RegisterResponse,
    VerifyRequest,
    LoginRequest,
    LoginResponse,
    AgentProfile,
    AgentUpdateRequest,
    AddAgentRequest,
    AddAgentResponse,
    AgentInfo,
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


@router.post("/register", response_model=RegisterPendingResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 1: Register an email + name.

    Input: email, name
    Output: { user_id, pending: true } + sends 6-digit code to email

    Creates an unverified user. The agent must then call /auth/verify
    with the code to complete registration and get an API key.

    In dev mode (no RESEND_API_KEY), the code is included in the response
    so agents can auto-verify without real email.
    """
    # Check if email already registered
    result = await db.execute(select(User).where(User.email == req.email))
    existing = result.scalar_one_or_none()

    if existing and existing.verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Generate a 6-digit verification code
    code = generate_verification_code()
    expires_at = utcnow() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES)

    if existing and not existing.verified:
        # Re-register: update the code and expiry (they never verified last time)
        existing.name = req.name
        existing.verification_code = code
        existing.verification_expires_at = expires_at
        user = existing
    else:
        # Brand new user — create unverified
        user = User(
            email=req.email,
            name=req.name,
            verified=False,
            verification_code=code,
            verification_expires_at=expires_at,
        )
        db.add(user)
        await db.flush()

    # Send the code via email (or skip in dev mode)
    await send_verification_email(req.email, code)

    # In dev mode (no Resend key), include the code so agents can auto-verify
    message = "Verification code sent to your email. Call /auth/verify with the code to complete registration."
    if not RESEND_API_KEY:
        message = f"Dev mode — your verification code is: {code}. Call /auth/verify to complete registration."

    return RegisterPendingResponse(
        user_id=user.id,
        message=message,
    )


@router.post("/verify", response_model=RegisterResponse)
async def verify(req: VerifyRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 2: Verify email and create the first agent.

    Input: email, 6-digit code, agent_name, optional framework/webhook_url
    Output: user_id, agent_id, and the API key (shown ONCE)

    The code must match and not be expired. Once verified, the user is
    marked as verified and their first agent is created with an API key.
    """
    # Find the user by email
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending registration for this email. Call /auth/register first.",
        )

    if user.verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already verified. Use /auth/login or /auth/agents to add another agent.",
        )

    # Check the verification code
    if user.verification_code != req.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    # Check expiry
    if user.verification_expires_at and utcnow() > user.verification_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Call /auth/register again to get a new code.",
        )

    # Mark user as verified and clear the code
    user.verified = True
    user.verification_code = None
    user.verification_expires_at = None

    # Generate API key and hash it
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    # Validate webhook URL if provided (SSRF protection)
    if req.webhook_url:
        _validate_webhook_url(req.webhook_url)

    # Create the first agent linked to user
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
    if not user.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Complete verification first.",
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


@router.post("/agents", response_model=AddAgentResponse)
async def add_agent(
    req: AddAgentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Add another agent to your account.

    Input: API key (existing agent) + agent_name, optional framework/webhook_url
    Output: new agent_id + API key (shown ONCE)

    Authenticated with an existing agent's API key. The new agent is linked
    to the same human (user_id). The new agent is NOT primary — only the
    first agent is primary by default.
    """
    # Validate webhook URL if provided (SSRF protection)
    if req.webhook_url:
        _validate_webhook_url(req.webhook_url)

    # Generate API key for the new agent
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    # Create new agent under the same user, not primary
    new_agent = Agent(
        user_id=agent.user_id,
        name=req.agent_name,
        api_key_hash=key_hash,
        framework=req.framework,
        webhook_url=req.webhook_url,
        is_primary=False,
    )
    db.add(new_agent)
    await db.flush()

    return AddAgentResponse(
        agent_id=new_agent.id,
        api_key=raw_key,
    )


@router.get("/agents", response_model=list)
async def list_agents(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    List all agents under your account.

    Input: API key (any of your agents)
    Output: list of AgentInfo for all agents belonging to the same human

    Shows which agents are primary, their frameworks, and status.
    """
    result = await db.execute(
        select(Agent).where(Agent.user_id == agent.user_id)
    )
    agents = result.scalars().all()
    return [AgentInfo.model_validate(a) for a in agents]
