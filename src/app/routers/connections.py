"""
Connection router — invite codes and connection management.

Connections are human-to-human. Any agent under a human can create invites,
accept invites, and list connections. When two humans connect, ALL of their
agents can communicate through that connection.

POST /connections/invite  → Generate an invite code
POST /connections/accept  → Accept an invite and create a connection
GET  /connections         → List all connections for the current human
DELETE /connections/{id}  → Remove a connection
"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import get_current_agent
from src.app.config import INVITE_EXPIRE_HOURS, BUILT_IN_CONTRACTS, DEFAULT_CONTRACT
from src.app.database import get_db
from src.app.models import Agent, User, Invite, Connection, Permission
from src.app.schemas import (
    InviteCreateResponse,
    InviteAcceptRequest,
    ConnectionInfo,
    ConnectedUserInfo,
    AgentInfo,
)

router = APIRouter(prefix="/connections", tags=["connections"])


@router.post("/invite", response_model=InviteCreateResponse)
async def create_invite(
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate an invite code.

    Input: (just the API key in header)
    Output: An invite code, a ready-to-share join URL, and expiry time

    The invite is created at the human level (from_user_id). Any of the
    human's agents can create invites — they all represent the same person.
    """
    code = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(hours=INVITE_EXPIRE_HOURS)

    # Invite is from the human, not the specific agent
    invite = Invite(
        code=code,
        from_user_id=agent.user_id,
        expires_at=expires_at,
    )
    db.add(invite)

    # Build the ready-to-share join URL
    base_url = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https":
        base_url = base_url.replace("http://", "https://", 1)
    join_url = f"{base_url}/join/{code}"

    return InviteCreateResponse(invite_code=code, join_url=join_url, expires_at=expires_at)


@router.post("/accept", response_model=ConnectionInfo)
async def accept_invite(
    req: InviteAcceptRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept an invite code to form a human-to-human connection.

    Input: invite_code + optional contract preset
    Output: The new connection info (connected human + all their agents)

    Creates a bidirectional connection between two humans. Both humans'
    agents can now communicate through this connection.
    """
    # Find the invite
    result = await db.execute(
        select(Invite).where(Invite.code == req.invite_code)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    if invite.used:
        raise HTTPException(status_code=400, detail="This invite has already been used")

    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This invite has expired")

    # Can't connect with yourself (same human)
    if invite.from_user_id == agent.user_id:
        raise HTTPException(status_code=400, detail="You can't connect with yourself")

    # Check if already connected (human-to-human)
    result = await db.execute(
        select(Connection).where(
            or_(
                and_(
                    Connection.user_a_id == invite.from_user_id,
                    Connection.user_b_id == agent.user_id,
                ),
                and_(
                    Connection.user_a_id == agent.user_id,
                    Connection.user_b_id == invite.from_user_id,
                ),
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Already connected with this person")

    # Validate the contract name
    contract_name = req.contract if req.contract else DEFAULT_CONTRACT
    if contract_name not in BUILT_IN_CONTRACTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown contract '{contract_name}'. Options: {', '.join(BUILT_IN_CONTRACTS)}",
        )
    contract_levels = BUILT_IN_CONTRACTS[contract_name]

    # Mark invite as used
    invite.used = True
    invite.used_by_user_id = agent.user_id

    # Create the human-to-human connection
    connection = Connection(
        user_a_id=invite.from_user_id,
        user_b_id=agent.user_id,
        contract_type=contract_name,
    )
    db.add(connection)
    await db.flush()

    # Create permissions for both humans from the contract preset.
    # Permissions are per-human, not per-agent — all agents under a human
    # share the same permission levels.
    for user_id in (invite.from_user_id, agent.user_id):
        for category, level in contract_levels.items():
            perm = Permission(
                connection_id=connection.id,
                user_id=user_id,
                category=category,
                level=level,
            )
            db.add(perm)
    await db.flush()

    # Load the other human's info + all their agents
    result = await db.execute(
        select(User).where(User.id == invite.from_user_id)
    )
    other_user = result.scalar_one()

    result = await db.execute(
        select(Agent).where(Agent.user_id == invite.from_user_id)
    )
    other_agents = result.scalars().all()

    return ConnectionInfo(
        id=connection.id,
        connected_user=ConnectedUserInfo(
            name=other_user.name,
            agents=[AgentInfo.model_validate(a) for a in other_agents],
        ),
        status=connection.status,
        contract_type=connection.contract_type,
        created_at=connection.created_at,
    )


@router.get("", response_model=list[ConnectionInfo])
async def list_connections(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    List all connections for the current human.

    Input: (just the API key — any of your agents)
    Output: List of connections with the other human's name + all their agents

    Returns active connections at the human level. Each connection shows
    who you're connected to and all of their agents.
    """
    user_id = agent.user_id

    # Find all connections where this human is either side
    result = await db.execute(
        select(Connection).where(
            or_(
                Connection.user_a_id == user_id,
                Connection.user_b_id == user_id,
            )
        )
    )
    connections = result.scalars().all()

    response = []
    for conn in connections:
        # Figure out who the "other" human is
        other_user_id = conn.user_b_id if conn.user_a_id == user_id else conn.user_a_id

        # Load their info
        result = await db.execute(select(User).where(User.id == other_user_id))
        other_user = result.scalar_one()

        # Load all their agents
        result = await db.execute(
            select(Agent).where(Agent.user_id == other_user_id)
        )
        other_agents = result.scalars().all()

        response.append(
            ConnectionInfo(
                id=conn.id,
                connected_user=ConnectedUserInfo(
                    name=other_user.name,
                    agents=[AgentInfo.model_validate(a) for a in other_agents],
                ),
                status=conn.status,
                contract_type=conn.contract_type or "friends",
                created_at=conn.created_at,
            )
        )

    return response


@router.delete("/{connection_id}", status_code=204)
async def remove_connection(
    connection_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a connection.

    Input: connection_id in URL
    Output: 204 No Content

    Either side of a connection can remove it. Uses user_id for auth.
    """
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if agent.user_id not in (connection.user_a_id, connection.user_b_id):
        raise HTTPException(status_code=403, detail="Not your connection")

    connection.status = "removed"
