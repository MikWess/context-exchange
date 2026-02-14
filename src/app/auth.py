"""
Authentication utilities.

Two auth mechanisms:
1. API key auth — for agents hitting the API (Bearer token in header)
2. JWT auth — for humans using the dashboard (cookie or header)

API keys are prefixed with "cex_" so they're easy to identify.
They're hashed with passlib before storage — the raw key is only returned once.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.hash import pbkdf2_sha256
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import (
    API_KEY_PREFIX,
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
)
from src.app.database import get_db
from src.app.models import Agent, User

# FastAPI security scheme — expects "Authorization: Bearer <token>" header
bearer_scheme = HTTPBearer()


# --- API Key utilities ---

def generate_api_key() -> str:
    """
    Generate a new API key.
    Format: cex_<32 random hex chars>
    Returns the raw key (show to user once, then never again).
    """
    return f"{API_KEY_PREFIX}{secrets.token_hex(32)}"


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for storage. Uses PBKDF2-SHA256."""
    return pbkdf2_sha256.hash(raw_key)


def verify_api_key(raw_key: str, hashed: str) -> bool:
    """Check a raw API key against its hash."""
    return pbkdf2_sha256.verify(raw_key, hashed)


# --- JWT utilities (for dashboard auth later) ---

def create_jwt_token(user_id: str) -> str:
    """Create a JWT token for dashboard login."""
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[str]:
    """Decode a JWT and return the user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# --- FastAPI dependencies ---

async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """
    FastAPI dependency — authenticates an agent via API key.
    Expects: Authorization: Bearer cex_<key>

    Returns the Agent ORM object if valid.
    Raises 401 if the key is missing, malformed, or doesn't match any agent.
    """
    token = credentials.credentials

    # Quick check: must start with our prefix
    if not token.startswith(API_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
        )

    # Look up all agents and check the key hash
    # (In prod with many agents, you'd want a key lookup table. Fine for MVP.)
    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    for agent in agents:
        if verify_api_key(token, agent.api_key_hash):
            # Update last_seen timestamp
            agent.last_seen_at = datetime.utcnow()
            return agent

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — authenticates a human via JWT.
    For dashboard endpoints.
    """
    token = credentials.credentials
    user_id = decode_jwt_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
