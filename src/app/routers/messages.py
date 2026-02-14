"""
Message router — sending and receiving context between agents.

POST /messages           → Send a message to a connected agent
GET  /messages/inbox     → Get unread messages (agent polls this)
POST /messages/{id}/ack  → Acknowledge receipt of a message
GET  /messages/thread/{id} → Get all messages in a thread
GET  /messages/threads   → List all threads for the current agent
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import get_current_agent
from src.app.database import get_db
from src.app.models import Agent, Connection, Thread, Message
from src.app.schemas import (
    SendMessageRequest,
    MessageInfo,
    InboxResponse,
    ThreadInfo,
    ThreadDetail,
)

router = APIRouter(prefix="/messages", tags=["messages"])


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


@router.post("", response_model=MessageInfo)
async def send_message(
    req: SendMessageRequest,
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

    message_infos = [MessageInfo.model_validate(m) for m in messages]
    return InboxResponse(messages=message_infos, count=len(message_infos))


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
