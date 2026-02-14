"""
Auth router — registration and login.

POST /auth/register  → Create a user + agent, return API key (agent calls this)
POST /auth/login     → Get a JWT for the dashboard (human calls this)
GET  /auth/me        → Get current agent's profile (agent calls this)
"""
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
)

router = APIRouter(prefix="/auth", tags=["auth"])


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

    # Create agent linked to user
    agent = Agent(
        user_id=user.id,
        name=req.agent_name,
        api_key_hash=key_hash,
        framework=req.framework,
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
    Output: Agent profile with id, name, framework, status, etc.

    Agents call this to verify their API key works and see their own info.
    """
    return AgentProfile.model_validate(agent)
