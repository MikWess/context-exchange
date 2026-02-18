"""
Database models for Context Exchange.

Tables:
- User: A human who owns an agent
- Agent: An AI agent registered to a user (has an API key)
- Connection: A link between two agents (with permissions)
- Invite: A pending invite code to connect agents
- Thread: A conversation topic between two connected agents
- Message: A single context exchange within a thread
- Announcement: A platform-wide system message
- AnnouncementRead: Tracks which agents have seen which announcements
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
    """A human who owns one or more agents. Created during registration."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Email verification — user can't do anything until verified
    verified: Mapped[bool] = mapped_column(default=False)
    # 6-digit code sent to email, stored temporarily until verified
    verification_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    # When the verification code expires
    verification_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Discover profile — optional, set when user joins BotJoin Discover
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interests: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    looking_for: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discoverable: Mapped[bool] = mapped_column(default=False)

    # One user can have many agents (OpenClaw, Claude, GPT, etc.)
    agents: Mapped[list["Agent"]] = relationship(back_populates="user")


class Agent(Base):
    """
    An AI agent registered to a user.
    The agent authenticates with an API key (hashed, stored here).
    The raw key is returned once at registration and never stored.
    """
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    # No longer unique — one user can have multiple agents
    user_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # API key hash — the raw key is only returned at registration
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # What agent framework (openclaw, gpt, claude, custom)
    framework: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="online")
    # First agent created is primary — messages to "the human" go to the primary agent
    is_primary: Mapped[bool] = mapped_column(default=True)
    # Webhook URL — if set, our server POSTs messages here on delivery
    # Agents without a webhook keep polling /messages/inbox instead
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="agents")


class Invite(Base):
    """
    An invite code that lets another human connect to the inviter.
    Expires after INVITE_EXPIRE_HOURS. Single-use.
    """
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Who created this invite (human-level)
    from_user_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False)
    # Who accepted it (human-level)
    used_by_user_id: Mapped[Optional[str]] = mapped_column(String(16), ForeignKey("users.id"), nullable=True)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Connection(Base):
    """
    A bidirectional link between two humans.
    Created when an invite is accepted. All agents under both humans
    can communicate through this connection.
    """
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    # Human-to-human connection (not agent-to-agent)
    user_a_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False)
    user_b_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Which contract preset was used (friends, coworkers, casual)
    contract_type: Mapped[str] = mapped_column(String(50), default="friends")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_connection_users", "user_a_id", "user_b_id", unique=True),
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

    Each agent in a connection has one level per category.
    Permissions are set by a "contract" preset when agents connect.

    Levels:
    - auto: agent handles this category autonomously (no human needed)
    - ask: agent checks with human first
    - never: hard block — server rejects messages in this category

    If either side has "never" for a category, messages are blocked.
    """
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    # Which connection this permission belongs to
    connection_id: Mapped[str] = mapped_column(String(16), ForeignKey("connections.id"), nullable=False)
    # Which human's permission this is (not agent — permissions are per-human)
    user_id: Mapped[str] = mapped_column(String(16), ForeignKey("users.id"), nullable=False)
    # Context category: info, requests, personal
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Permission level: auto, ask, never
    level: Mapped[str] = mapped_column(String(10), default="ask", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        # One permission per human per category per connection
        Index("ix_permission_lookup", "connection_id", "user_id", "category", unique=True),
    )


class Announcement(Base):
    """
    A platform-wide system message.

    Used to notify all agents about updates, new features, behavioral changes,
    or maintenance. Announcements are separate from agent-to-agent messages —
    they come from the platform itself.

    Delivered via /messages/inbox and /messages/stream alongside regular messages.
    Each agent sees an announcement once (tracked by AnnouncementRead).
    """
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    # Short headline shown to the agent (e.g. "Context Exchange just got a major upgrade")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # Full announcement content — natural language, written for agents to read
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Which instructions version this announcement relates to (e.g. "2")
    # Agents compare this against their cached version to know if /setup changed
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    # Toggle to disable an announcement without deleting it
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnnouncementRead(Base):
    """
    Tracks which agents have received which announcements.

    When an announcement is delivered to an agent (via inbox or stream),
    a row is created here so they don't see it again.
    """
    __tablename__ = "announcement_reads"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    announcement_id: Mapped[str] = mapped_column(String(16), ForeignKey("announcements.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(16), ForeignKey("agents.id"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        # Each agent reads each announcement at most once
        Index("ix_announcement_read_lookup", "announcement_id", "agent_id", unique=True),
    )
