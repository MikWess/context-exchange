"""
Pydantic schemas — define what goes in and what comes out of every endpoint.

Naming convention:
- *Request = what the client sends
- *Response = what the server returns
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# --- Auth / Registration ---

class RegisterRequest(BaseModel):
    """Agent sends this to create a user + agent in one step."""
    email: str = Field(description="Human's email address")
    name: str = Field(description="Human's display name")
    agent_name: str = Field(description="What the agent calls itself")
    framework: Optional[str] = Field(None, description="Agent framework: openclaw, gpt, claude, custom")
    webhook_url: Optional[str] = Field(None, description="URL to receive webhook notifications when messages arrive")


class RegisterResponse(BaseModel):
    """Returned once at registration. The api_key is NEVER shown again."""
    user_id: str
    agent_id: str
    api_key: str = Field(description="Store this securely — it won't be shown again")
    message: str = "Registration successful. Save your API key — it cannot be retrieved later."


class LoginRequest(BaseModel):
    """Human dashboard login (email-based for MVP, OAuth later)."""
    email: str


class LoginResponse(BaseModel):
    """JWT token for dashboard access."""
    token: str
    user_id: str
    name: str


# --- Agent ---

class AgentInfo(BaseModel):
    """Public info about an agent (shared with connections)."""
    id: str
    name: str
    framework: Optional[str]
    status: str
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentProfile(BaseModel):
    """Full agent profile (returned to the agent itself)."""
    id: str
    user_id: str
    name: str
    framework: Optional[str]
    status: str
    webhook_url: Optional[str]
    last_seen_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentUpdateRequest(BaseModel):
    """Update agent settings (e.g. webhook URL)."""
    webhook_url: Optional[str] = Field(None, description="URL to receive webhook notifications. Set to empty string to clear.")


# --- Connections ---

class InviteCreateResponse(BaseModel):
    """Returned when an agent generates an invite."""
    invite_code: str
    join_url: str
    expires_at: datetime
    message: str = "Share this join_url with the person you want to connect with. Their agent fetches it and gets full setup instructions."


class InviteAcceptRequest(BaseModel):
    """Another agent sends this to accept an invite."""
    invite_code: str
    contract: str = Field("friends", description="Permission preset: friends, coworkers, or casual")


class ConnectionInfo(BaseModel):
    """Info about a connection (from one agent's perspective)."""
    id: str
    connected_agent: AgentInfo
    status: str
    contract_type: str = "friends"
    created_at: datetime


# --- Messages ---

class SendMessageRequest(BaseModel):
    """Agent sends context to a connected agent."""
    to_agent_id: str = Field(description="The recipient agent's ID")
    content: str = Field(description="The context/message content")
    message_type: str = Field("text", description="Type: text, query, response, update, request")
    category: Optional[str] = Field(None, description="Context category: schedule, projects, knowledge, etc.")
    thread_id: Optional[str] = Field(None, description="Existing thread ID, or omit to create a new one")
    thread_subject: Optional[str] = Field(None, description="Subject for a new thread (ignored if thread_id is set)")


class MessageInfo(BaseModel):
    """A single message as returned by the API."""
    id: str
    thread_id: str
    from_agent_id: str
    to_agent_id: str
    message_type: str
    category: Optional[str]
    content: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AnnouncementInfo(BaseModel):
    """A platform announcement — system messages about updates, new features, etc."""
    id: str
    title: str
    content: str
    version: str
    created_at: datetime
    # Fixed source field — always "context-exchange-platform".
    # This distinguishes announcements from agent messages structurally.
    # Only the server can set this field — agents cannot inject announcements.
    source: str = "context-exchange-platform"

    model_config = ConfigDict(from_attributes=True)


class InboxResponse(BaseModel):
    """List of unread messages for the agent, plus platform announcements."""
    messages: List[MessageInfo]
    count: int
    # Platform announcements — unread system messages about updates/features
    announcements: List[AnnouncementInfo] = []
    # Current platform instructions version — agents compare against their cached
    # version to know when to re-fetch /setup for updated instructions
    instructions_version: str = "1"


class ThreadInfo(BaseModel):
    """Summary info about a thread."""
    id: str
    connection_id: str
    subject: Optional[str]
    status: str
    created_at: datetime
    last_message_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ThreadDetail(BaseModel):
    """Full thread with all messages."""
    thread: ThreadInfo
    messages: List[MessageInfo]


# --- Permissions ---

class PermissionInfo(BaseModel):
    """A single permission: one category's level for one agent on one connection."""
    category: str
    level: str  # auto, ask, never

    model_config = ConfigDict(from_attributes=True)


class PermissionListResponse(BaseModel):
    """All permissions for a connection (from one agent's perspective)."""
    connection_id: str
    permissions: List[PermissionInfo]


class PermissionUpdateRequest(BaseModel):
    """Update the permission level for one category."""
    category: str = Field(description="Context category: info, requests, or personal")
    level: str = Field(description="Permission level: auto, ask, or never")


class ContractInfo(BaseModel):
    """A permission preset showing what each category defaults to."""
    name: str
    levels: dict  # {"info": "auto", "requests": "ask", "personal": "ask"}


# --- Admin ---

class CreateAnnouncementRequest(BaseModel):
    """Admin creates a platform announcement."""
    title: str = Field(description="Short headline for the announcement")
    content: str = Field(description="Full announcement content (natural language, markdown OK)")
    version: str = Field(description="Instructions version this relates to (e.g. '2')")
