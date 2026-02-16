"""
Connection router — invite codes and connection management.

POST /connections/invite  → Generate an invite code
POST /connections/accept  → Accept an invite and create a connection
GET  /connections         → List all connections for the current agent
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
from src.app.models import Agent, Invite, Connection, Permission
from src.app.schemas import (
    InviteCreateResponse,
    InviteAcceptRequest,
    ConnectionInfo,
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

    The agent shares the join_url with another person. Their agent fetches
    it and gets full setup instructions with the invite code baked in.
    Codes are single-use and expire after INVITE_EXPIRE_HOURS.
    """
    code = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(hours=INVITE_EXPIRE_HOURS)

    invite = Invite(
        code=code,
        from_agent_id=agent.id,
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
    Accept an invite code to form a connection.

    Input: invite_code
    Output: The new connection info

    Validates the code is real, not expired, not used, and not from yourself.
    Creates a bidirectional connection between the two agents.
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

    if invite.from_agent_id == agent.id:
        raise HTTPException(status_code=400, detail="You can't connect with yourself")

    # Check if already connected
    result = await db.execute(
        select(Connection).where(
            or_(
                and_(
                    Connection.agent_a_id == invite.from_agent_id,
                    Connection.agent_b_id == agent.id,
                ),
                and_(
                    Connection.agent_a_id == agent.id,
                    Connection.agent_b_id == invite.from_agent_id,
                ),
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Already connected with this agent")

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
    invite.used_by_agent_id = agent.id

    # Create the connection with the chosen contract
    connection = Connection(
        agent_a_id=invite.from_agent_id,
        agent_b_id=agent.id,
        contract_type=contract_name,
    )
    db.add(connection)
    await db.flush()

    # Create permissions for both agents from the contract preset.
    # Both agents get the same starting levels — either can customize later.
    for agent_id in (invite.from_agent_id, agent.id):
        for category, level in contract_levels.items():
            perm = Permission(
                connection_id=connection.id,
                agent_id=agent_id,
                category=category,
                level=level,
            )
            db.add(perm)
    await db.flush()

    # Load the other agent's info to return
    result = await db.execute(
        select(Agent).where(Agent.id == invite.from_agent_id)
    )
    other_agent = result.scalar_one()

    return ConnectionInfo(
        id=connection.id,
        connected_agent=AgentInfo.model_validate(other_agent),
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
    List all connections for the current agent.

    Input: (just the API key)
    Output: List of connections with the other agent's info

    Returns active connections. Each connection shows the other agent's
    name, framework, status, and when they were last seen.
    """
    # Find all connections where this agent is either side
    result = await db.execute(
        select(Connection).where(
            or_(
                Connection.agent_a_id == agent.id,
                Connection.agent_b_id == agent.id,
            )
        )
    )
    connections = result.scalars().all()

    response = []
    for conn in connections:
        # Figure out who the "other" agent is
        other_id = conn.agent_b_id if conn.agent_a_id == agent.id else conn.agent_a_id
        result = await db.execute(select(Agent).where(Agent.id == other_id))
        other_agent = result.scalar_one()

        response.append(
            ConnectionInfo(
                id=conn.id,
                connected_agent=AgentInfo.model_validate(other_agent),
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

    Either side of a connection can remove it.
    """
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if agent.id not in (connection.agent_a_id, connection.agent_b_id):
        raise HTTPException(status_code=403, detail="Not your connection")

    connection.status = "removed"
