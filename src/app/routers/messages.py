"""
Message router — sending and receiving context between agents.

POST /messages           → Send a message to a connected agent
GET  /messages/inbox     → Get unread messages (agent polls this)
POST /messages/{id}/ack  → Acknowledge receipt of a message
GET  /messages/thread/{id} → Get all messages in a thread
GET  /messages/threads   → List all threads for the current agent
"""
import asyncio
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import get_current_agent
from src.app.config import INSTRUCTIONS_VERSION
from src.app.database import get_db
from src.app.models import Agent, Connection, Thread, Message, Permission, Announcement, AnnouncementRead

logger = logging.getLogger(__name__)
from src.app.schemas import (
    SendMessageRequest,
    MessageInfo,
    InboxResponse,
    AnnouncementInfo,
    ThreadInfo,
    ThreadDetail,
)

router = APIRouter(prefix="/messages", tags=["messages"])


async def _deliver_webhook(webhook_url: str, payload: dict):
    """
    Fire-and-forget webhook delivery.

    POSTs the message payload to the agent's webhook URL.
    If it fails, we log it but don't error — the message is still in the
    inbox for polling as a fallback.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            logger.info(f"Webhook delivered to {webhook_url}: {resp.status_code}")
    except Exception as e:
        # Webhook failure is not fatal — message is still in the inbox
        logger.warning(f"Webhook delivery failed for {webhook_url}: {e}")


async def _verify_connection(
    agent_id: str, other_agent_id: str, db: AsyncSession
) -> Connection:
    """
    Check that two agents are connected. Returns the connection.
    Raises 403 if not connected.
    """
    result = await db.execute(
        select(Connection).where(
            Connection.status == "active",
            or_(
                and_(
                    Connection.agent_a_id == agent_id,
                    Connection.agent_b_id == other_agent_id,
                ),
                and_(
                    Connection.agent_a_id == other_agent_id,
                    Connection.agent_b_id == agent_id,
                ),
            ),
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(
            status_code=403,
            detail="Not connected with this agent. Send an invite first.",
        )
    return connection


async def _get_unread_announcements(agent_id: str, db: AsyncSession) -> list:
    """
    Get all active announcements this agent hasn't seen yet.

    Queries for announcements that are active and don't have a read record
    for this agent. Creates AnnouncementRead rows so they won't be returned
    again on the next call.

    Returns a list of AnnouncementInfo schemas.
    """
    # Find announcements this agent hasn't read yet
    # Subquery: announcement IDs this agent has already read
    read_subquery = (
        select(AnnouncementRead.announcement_id)
        .where(AnnouncementRead.agent_id == agent_id)
    )

    result = await db.execute(
        select(Announcement)
        .where(
            Announcement.is_active == True,
            Announcement.id.not_in(read_subquery),
        )
        .order_by(Announcement.created_at)
    )
    announcements = result.scalars().all()

    # Mark them as read so they don't show up again
    for ann in announcements:
        read_record = AnnouncementRead(
            announcement_id=ann.id,
            agent_id=agent_id,
        )
        db.add(read_record)

    return [AnnouncementInfo.model_validate(a) for a in announcements]


@router.post("", response_model=MessageInfo)
async def send_message(
    req: SendMessageRequest,
    background_tasks: BackgroundTasks,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message (context) to a connected agent.

    Input: to_agent_id, content, optional type/category/thread
    Output: The created message

    If thread_id is provided, adds to that thread.
    If not, creates a new thread (optionally with a subject).
    Only works if the two agents are connected.
    """
    # Can't message yourself
    if req.to_agent_id == agent.id:
        raise HTTPException(status_code=400, detail="Can't send a message to yourself")

    # Verify the recipient exists
    result = await db.execute(select(Agent).where(Agent.id == req.to_agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Recipient agent not found")

    # Verify connection
    connection = await _verify_connection(agent.id, req.to_agent_id, db)

    # Check permissions — if the message has a category, verify the sender
    # is allowed to share that category on this connection.
    # Messages with no category (plain text chat) always go through.
    if req.category:
        result = await db.execute(
            select(Permission).where(
                Permission.connection_id == connection.id,
                Permission.agent_id == agent.id,
                Permission.category == req.category,
            )
        )
        permission = result.scalar_one_or_none()
        # If permission exists and is "never", block the message
        if permission and permission.level == "never":
            raise HTTPException(
                status_code=403,
                detail=f"You don't have permission to share {req.category} with this connection",
            )

        # Inbound check — does the RECEIVER accept this category?
        result = await db.execute(
            select(Permission).where(
                Permission.connection_id == connection.id,
                Permission.agent_id == req.to_agent_id,
                Permission.category == req.category,
            )
        )
        inbound_perm = result.scalar_one_or_none()
        if inbound_perm and inbound_perm.inbound_level == "never":
            # Vague error — don't reveal the receiver's permission settings
            raise HTTPException(
                status_code=403,
                detail="Message could not be delivered",
            )

    # Get or create thread
    if req.thread_id:
        # Verify thread exists and belongs to this connection
        result = await db.execute(
            select(Thread).where(Thread.id == req.thread_id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        if thread.connection_id != connection.id:
            raise HTTPException(status_code=403, detail="Thread doesn't belong to this connection")
    else:
        # Create a new thread
        thread = Thread(
            connection_id=connection.id,
            subject=req.thread_subject,
        )
        db.add(thread)
        await db.flush()

    # Create the message
    message = Message(
        thread_id=thread.id,
        from_agent_id=agent.id,
        to_agent_id=req.to_agent_id,
        message_type=req.message_type,
        category=req.category,
        content=req.content,
    )
    db.add(message)

    # Update thread's last_message_at
    thread.last_message_at = message.created_at

    await db.flush()

    # Webhook delivery — if the recipient has a webhook URL, push the message
    # to them instantly instead of waiting for them to poll
    result = await db.execute(select(Agent).where(Agent.id == req.to_agent_id))
    recipient = result.scalar_one()
    if recipient.webhook_url:
        # Build the payload matching MessageInfo schema
        payload = MessageInfo.model_validate(message).model_dump(mode="json")
        background_tasks.add_task(_deliver_webhook, recipient.webhook_url, payload)

    return MessageInfo.model_validate(message)


@router.get("/inbox", response_model=InboxResponse)
async def get_inbox(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get unread messages for the current agent.

    Input: API key + optional limit
    Output: List of undelivered messages, newest first

    Agents poll this endpoint to check for new context.
    Messages with status "sent" are returned and marked as "delivered".
    """
    result = await db.execute(
        select(Message)
        .where(
            Message.to_agent_id == agent.id,
            Message.status == "sent",
        )
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    messages = result.scalars().all()

    # Mark as delivered
    for msg in messages:
        msg.status = "delivered"

    # Check for platform announcements this agent hasn't seen
    announcements = await _get_unread_announcements(agent.id, db)

    message_infos = [MessageInfo.model_validate(m) for m in messages]
    return InboxResponse(
        messages=message_infos,
        count=len(message_infos),
        announcements=announcements,
        instructions_version=INSTRUCTIONS_VERSION,
    )


@router.get("/stream", response_model=InboxResponse)
async def stream_messages(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    timeout: int = Query(30, ge=1, le=60, description="How long to wait for messages (seconds)"),
):
    """
    Long-polling endpoint — wait for new messages in real time.

    Input: API key + optional timeout (1-60 seconds, default 30)
    Output: New messages as soon as they arrive, or empty after timeout

    This is the recommended way to listen for messages. Your agent calls
    this in a loop:

    1. GET /messages/stream?timeout=30
    2. Server holds the connection open, checking every 2 seconds
    3. As soon as a message arrives → returned immediately
    4. If nothing arrives in 30 seconds → returns empty {messages: [], count: 0}
    5. Your agent immediately calls /messages/stream again → loop continues

    Works from any device, behind any firewall. No public URL needed.
    Messages are marked as "delivered" when returned, just like /messages/inbox.
    """
    # Check every 2 seconds for new messages
    poll_interval = 2
    elapsed = 0

    while elapsed < timeout:
        # Check for unread messages
        result = await db.execute(
            select(Message)
            .where(
                Message.to_agent_id == agent.id,
                Message.status == "sent",
            )
            .order_by(desc(Message.created_at))
            .limit(50)
        )
        messages = result.scalars().all()

        # Also check for unread announcements on each iteration
        announcements = await _get_unread_announcements(agent.id, db)

        if messages or announcements:
            # Found something — mark messages as delivered and return
            for msg in messages:
                msg.status = "delivered"
            await db.commit()

            message_infos = [MessageInfo.model_validate(m) for m in messages]
            return InboxResponse(
                messages=message_infos,
                count=len(message_infos),
                announcements=announcements,
                instructions_version=INSTRUCTIONS_VERSION,
            )

        # No messages or announcements yet — wait and try again
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        # Expire any cached state so we see new rows on next query
        db.expire_all()

    # Timeout reached — return empty (still include version for agents to check)
    return InboxResponse(
        messages=[],
        count=0,
        instructions_version=INSTRUCTIONS_VERSION,
    )


@router.post("/{message_id}/ack")
async def acknowledge_message(
    message_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Acknowledge receipt of a message.

    Input: message_id in URL
    Output: { "status": "acknowledged" }

    The receiving agent calls this after processing a message.
    Updates the message status from "delivered" to "read".
    """
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.to_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not your message")

    message.status = "read"
    message.acknowledged_at = datetime.utcnow()

    return {"status": "acknowledged"}


@router.get("/threads", response_model=list[ThreadInfo])
async def list_threads(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    List all threads the current agent is part of.

    Input: API key
    Output: List of threads with subject, status, last activity

    Returns threads from all connections, sorted by most recent activity.
    """
    # Find all connections for this agent
    result = await db.execute(
        select(Connection.id).where(
            Connection.status == "active",
            or_(
                Connection.agent_a_id == agent.id,
                Connection.agent_b_id == agent.id,
            ),
        )
    )
    connection_ids = [row[0] for row in result.all()]

    if not connection_ids:
        return []

    # Get threads for these connections
    result = await db.execute(
        select(Thread)
        .where(Thread.connection_id.in_(connection_ids))
        .order_by(desc(Thread.last_message_at))
    )
    threads = result.scalars().all()

    return [ThreadInfo.model_validate(t) for t in threads]


@router.get("/thread/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a full thread with all messages.

    Input: thread_id in URL
    Output: Thread info + all messages in order

    This is the "debug view" — see the complete conversation between two agents.
    """
    # Get the thread
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Verify this agent is part of the connection
    result = await db.execute(
        select(Connection).where(Connection.id == thread.connection_id)
    )
    connection = result.scalar_one()
    if agent.id not in (connection.agent_a_id, connection.agent_b_id):
        raise HTTPException(status_code=403, detail="Not your thread")

    # Get all messages in the thread
    result = await db.execute(
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()

    return ThreadDetail(
        thread=ThreadInfo.model_validate(thread),
        messages=[MessageInfo.model_validate(m) for m in messages],
    )
