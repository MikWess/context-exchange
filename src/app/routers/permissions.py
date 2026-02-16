"""
Permission router — view and update per-connection, per-category sharing rules.

GET  /connections/{id}/permissions  → List all permission settings for a connection
PUT  /connections/{id}/permissions  → Update one category's permission level
GET  /contracts                    → List available contract presets

Each agent controls their own permission level per category.
If either side has "never" for a category, messages in that category are blocked.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import get_current_agent
from src.app.config import DEFAULT_CATEGORIES, VALID_PERMISSION_LEVELS, BUILT_IN_CONTRACTS
from src.app.database import get_db
from src.app.models import Agent, Connection, Permission
from src.app.schemas import (
    ContractInfo,
    PermissionInfo,
    PermissionListResponse,
    PermissionUpdateRequest,
)

router = APIRouter(tags=["permissions"])


def _verify_user_in_connection(agent: Agent, connection: Connection):
    """Check that the agent's human is part of this connection. Raises 403 if not."""
    if agent.user_id not in (connection.user_a_id, connection.user_b_id):
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
    Output: List of {category, level} for every category (info, requests, personal)

    Shows YOUR permission levels for this connection.
    """
    # Verify connection exists
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id)
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Verify this agent is part of the connection
    _verify_user_in_connection(agent, connection)

    # Get all permissions for this agent on this connection
    result = await db.execute(
        select(Permission).where(
            Permission.connection_id == connection_id,
            Permission.user_id == agent.user_id,
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

    Input: connection_id in URL + {category, level} in body + API key
    Output: The updated permission

    Changes YOUR permission level for this category on this connection.
    Valid levels: auto (handle autonomously), ask (check with human), never (blocked).
    """
    # Validate the level
    if req.level not in VALID_PERMISSION_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level '{req.level}'. Must be one of: {', '.join(sorted(VALID_PERMISSION_LEVELS))}",
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
    _verify_user_in_connection(agent, connection)

    # Find the permission row for this category
    result = await db.execute(
        select(Permission).where(
            Permission.connection_id == connection_id,
            Permission.user_id == agent.user_id,
            Permission.category == req.category,
        )
    )
    permission = result.scalar_one_or_none()
    if not permission:
        raise HTTPException(
            status_code=404,
            detail=f"Permission for category '{req.category}' not found",
        )

    # Update the level
    permission.level = req.level

    return PermissionInfo.model_validate(permission)


@router.get("/contracts", response_model=list[ContractInfo])
async def list_contracts():
    """
    List available permission contracts (presets).

    Input: none (no auth required)
    Output: List of contract names with their category levels

    Contracts are permission presets applied when two agents connect.
    Each contract defines a default level for each category (info, requests, personal).
    """
    return [
        ContractInfo(name=name, levels=levels)
        for name, levels in BUILT_IN_CONTRACTS.items()
    ]
