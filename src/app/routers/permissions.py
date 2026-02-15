"""
Permission router — view and update per-connection, per-category sharing rules.

GET  /connections/{id}/permissions  → List all permission settings for a connection
PUT  /connections/{id}/permissions  → Update one category's permission level

Each agent controls their own outbound sharing. When you check permissions,
you see YOUR settings for that connection. When you update, you're changing
YOUR own sharing rules — not the other agent's.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import get_current_agent
from src.app.config import DEFAULT_CATEGORIES, VALID_PERMISSION_LEVELS
from src.app.database import get_db
from src.app.models import Agent, Connection, Permission
from src.app.schemas import (
    PermissionInfo,
    PermissionListResponse,
    PermissionUpdateRequest,
)

router = APIRouter(tags=["permissions"])


def _verify_agent_in_connection(agent: Agent, connection: Connection):
    """Check that the agent is part of this connection. Raises 403 if not."""
    if agent.id not in (connection.agent_a_id, connection.agent_b_id):
        raise HTTPException(status_code=403, detail="Not your connection")


@router.get("/connections/{connection_id}/permissions", response_model=PermissionListResponse)
async def get_permissions(
    connection_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all permission settings for a connection.

    Input: connection_id in URL + API key
    Output: List of {category, level, inbound_level} for every category

    Shows YOUR outbound and inbound rules for this connection.
    """
    # Verify connection exists
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Verify this agent is part of the connection
    _verify_agent_in_connection(agent, connection)

    # Get all permissions for this agent on this connection
    result = await db.execute(
        select(Permission).where(
            Permission.connection_id == connection_id,
            Permission.agent_id == agent.id,
        )
    )
    permissions = result.scalars().all()

    return PermissionListResponse(
        connection_id=connection_id,
        permissions=[PermissionInfo.model_validate(p) for p in permissions],
    )


@router.put("/connections/{connection_id}/permissions", response_model=PermissionInfo)
async def update_permission(
    connection_id: str,
    req: PermissionUpdateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a permission level for one category.

    Input: connection_id in URL + {category, level?, inbound_level?} in body + API key
    Output: The updated permission

    Changes YOUR outbound and/or inbound rules for this category.
    Valid levels: auto (share freely), ask (check with human), never (blocked).
    At least one of level or inbound_level must be provided.
    """
    # Must update at least one field
    if req.level is None and req.inbound_level is None:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one of: level, inbound_level",
        )

    # Validate outbound level if provided
    if req.level is not None and req.level not in VALID_PERMISSION_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level '{req.level}'. Must be one of: {', '.join(sorted(VALID_PERMISSION_LEVELS))}",
        )

    # Validate inbound level if provided
    if req.inbound_level is not None and req.inbound_level not in VALID_PERMISSION_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid inbound_level '{req.inbound_level}'. Must be one of: {', '.join(sorted(VALID_PERMISSION_LEVELS))}",
        )

    # Validate the category
    if req.category not in DEFAULT_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{req.category}'. Must be one of: {', '.join(DEFAULT_CATEGORIES)}",
        )

    # Verify connection exists
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Verify this agent is part of the connection
    _verify_agent_in_connection(agent, connection)

    # Find the permission row for this category
    result = await db.execute(
        select(Permission).where(
            Permission.connection_id == connection_id,
            Permission.agent_id == agent.id,
            Permission.category == req.category,
        )
    )
    permission = result.scalar_one_or_none()
    if not permission:
        raise HTTPException(
            status_code=404,
            detail=f"Permission for category '{req.category}' not found",
        )

    # Update whichever fields were provided
    if req.level is not None:
        permission.level = req.level
    if req.inbound_level is not None:
        permission.inbound_level = req.inbound_level

    return PermissionInfo.model_validate(permission)
