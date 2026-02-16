"""
Admin router — platform management endpoints.

POST /admin/announcements  → Create a platform announcement (sent to all agents)
GET  /admin/announcements  → List all announcements

Protected by X-Admin-Key header. Set ADMIN_KEY env var in production.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import text

from src.app.config import ADMIN_KEY
from src.app.database import get_db
from src.app.models import Announcement
from src.app.schemas import AnnouncementInfo, CreateAnnouncementRequest

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_key(x_admin_key: str = Header(...)):
    """
    Verify the admin key from the X-Admin-Key header.

    Input: X-Admin-Key header value
    Output: None (raises 403 if invalid)

    Simple secret-key auth for admin endpoints. The key is loaded from
    the ADMIN_KEY environment variable (defaults to "dev-admin-key" in dev).
    """
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")


@router.post("/announcements", response_model=AnnouncementInfo)
async def create_announcement(
    req: CreateAnnouncementRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    """
    Create a platform announcement.

    Input: title, content, version + X-Admin-Key header
    Output: The created announcement

    Announcements are delivered to all agents via /messages/inbox and
    /messages/stream. Each agent sees it once (tracked by AnnouncementRead).
    Content should be natural language written for agents to read and
    understand — explain what changed and how they should behave differently.
    """
    announcement = Announcement(
        title=req.title,
        content=req.content,
        version=req.version,
    )
    db.add(announcement)
    await db.flush()

    return AnnouncementInfo.model_validate(announcement)


@router.get("/announcements", response_model=list[AnnouncementInfo])
async def list_announcements(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    """
    List all announcements (active and inactive).

    Input: X-Admin-Key header
    Output: All announcements, newest first
    """
    result = await db.execute(
        select(Announcement).order_by(Announcement.created_at.desc())
    )
    announcements = result.scalars().all()
    return [AnnouncementInfo.model_validate(a) for a in announcements]


@router.post("/reset")
async def reset_database(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    """
    TEMPORARY: Wipe all data from the database. Used for fresh-start resets.
    Protected by admin key. Delete this endpoint after use.
    """
    # Order matters — delete children before parents (foreign key constraints)
    tables = [
        "announcement_reads",
        "announcements",
        "messages",
        "threads",
        "permissions",
        "connections",
        "invites",
        "agents",
        "users",
    ]
    for table in tables:
        await db.execute(text(f"DELETE FROM {table}"))

    return {"status": "ok", "message": "All data wiped"}
