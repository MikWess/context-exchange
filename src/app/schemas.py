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
    last_seen_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Connections ---

class InviteCreateResponse(BaseModel):
    """Returned when an agent generates an invite."""
    invite_code: str
    expires_at: datetime
    message: str = "Share this code with the agent you want to connect with."


class InviteAcceptRequest(BaseModel):
    """Another agent sends this to accept an invite."""
    invite_code: str


class ConnectionInfo(BaseModel):
    """Info about a connection (from one agent's perspective)."""
    id: str
    connected_agent: AgentInfo
    status: str
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


class InboxResponse(BaseModel):
    """List of unread messages for the agent."""
    messages: List[MessageInfo]
    count: int


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
