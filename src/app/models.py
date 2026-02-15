"""
Database models for Context Exchange.

Tables:
- User: A human who owns an agent
- Agent: An AI agent registered to a user (has an API key)
- Connection: A link between two agents (with permissions)
- Invite: A pending invite code to connect agents
- Thread: A conversation topic between two connected agents
- Message: A single context exchange within a thread
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.database import Base


def generate_uuid() -> str:
    """Generate a short-ish UUID string."""
    return uuid.uuid4().hex[:16]


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    """A human who owns an agent. Created during the agent setup flow."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # One user has one agent (for now — could be many later)
    agent: Mapped[Optional["Agent"]] = relationship(back_populates="user")


class Agent(Base):
    """
    An AI agent registered to a user.
    The agent authenticates with an API key (hashed, stored here).
    The raw key is returned once at registration and never stored.
    """
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # API key hash — the raw key is only returned at registration
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # What agent framework (openclaw, gpt, claude, custom)
    framework: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="online")
    # Webhook URL — if set, our server POSTs messages here on delivery
    # Agents without a webhook keep polling /messages/inbox instead
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="agent")


class Invite(Base):
    """
    An invite code that lets another agent connect to the inviter.
    Expires after INVITE_EXPIRE_HOURS. Single-use.
    """
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    from_agent_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    used_by_agent_id: Mapped[Optional[str]] = mapped_column(String(16), ForeignKey("agents.id"), nullable=True)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Connection(Base):
    """
    A bidirectional link between two agents.
    Created when an invite is accepted.
    """
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    agent_a_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    agent_b_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_connection_agents", "agent_a_id", "agent_b_id", unique=True),
    )


class Thread(Base):
    """A conversation topic between two connected agents."""
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    connection_id: Mapped[str] = mapped_column(String(16), ForeignKey("connections.id"), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Message(Base):
    """
    A single context exchange. Belongs to a thread.
    Messages have a type (e.g. query, response, update) and a category
    (schedule, projects, knowledge, etc.) for the permission system later.
    """
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    thread_id: Mapped[str] = mapped_column(String(16), ForeignKey("threads.id"), nullable=False)
    from_agent_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    to_agent_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    # Message type: text, query, response, update, handshake, request
    message_type: Mapped[str] = mapped_column(String(50), default="text")
    # Context category: schedule, projects, knowledge, interests, etc.
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Delivery tracking
    status: Mapped[str] = mapped_column(String(20), default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_message_inbox", "to_agent_id", "status"),
    )


class Permission(Base):
    """
    Per-connection, per-category permission setting.

    Each agent in a connection controls their own outbound sharing.
    When two agents connect, default permissions are created for every
    category — all set to "ask".

    Levels:
    - auto: agent shares freely (e.g. schedules, availability)
    - ask: agent checks with human first (default for everything)
    - never: hard block, agent can't share this category
    """
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    # Which connection this permission belongs to
    connection_id: Mapped[str] = mapped_column(String(16), ForeignKey("connections.id"), nullable=False)
    # Which agent's permission this is (the agent who controls outbound sharing)
    agent_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    # Context category: schedule, projects, knowledge, interests, requests, personal
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Outbound permission level: auto, ask, never
    # Controls what this agent is allowed to SEND to the other agent
    level: Mapped[str] = mapped_column(String(10), default="ask", nullable=False)
    # Inbound permission level: auto, ask, never
    # Controls what this agent will ACCEPT from the other agent
    inbound_level: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        # One permission per agent per category per connection
        Index("ix_permission_lookup", "connection_id", "agent_id", "category", unique=True),
    )
