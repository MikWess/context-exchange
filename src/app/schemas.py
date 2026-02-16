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
    """
    Step 1: Register an email + name. Sends a 6-digit verification code.
    No agent is created yet — that happens after verification.
    """
    email: str = Field(description="Human's email address")
    name: str = Field(description="Human's display name")


class RegisterPendingResponse(BaseModel):
    """Returned after registration — tells the caller to check email for the code."""
    user_id: str
    pending: bool = True
    message: str = "Verification code sent to your email. Call /auth/verify with the code to complete registration."


class VerifyRequest(BaseModel):
    """
    Step 2: Verify email with the 6-digit code, optionally create the first agent.

    If agent_name is provided, creates an agent and returns an API key.
    If omitted, just verifies the human (no agent created). This supports
    humans signing up through the Observer without needing an agent yet.
    """
    email: str = Field(description="The email you registered with")
    code: str = Field(description="6-digit verification code from your email")
    agent_name: Optional[str] = Field(None, description="What the agent calls itself (omit to verify without creating an agent)")
    framework: Optional[str] = Field(None, description="Agent framework: openclaw, gpt, claude, custom")
    webhook_url: Optional[str] = Field(None, description="URL to receive webhook notifications when messages arrive")


class RegisterResponse(BaseModel):
    """Returned after verification. If an agent was created, api_key is shown ONCE."""
    user_id: str
    agent_id: Optional[str] = Field(None, description="Only present if agent_name was provided")
    api_key: Optional[str] = Field(None, description="Store this securely — it won't be shown again")
    message: str = "Verification successful."


class LoginRequest(BaseModel):
    """Step 1: Request a login verification code (sent to email)."""
    email: str


class LoginPendingResponse(BaseModel):
    """Returned after login step 1 — tells the caller to check email for the code."""
    message: str = "Verification code sent to your email. Call /auth/login/verify with the code."


class LoginVerifyRequest(BaseModel):
    """Step 2: Verify the code and get a JWT token."""
    email: str = Field(description="Your registered email address")
    code: str = Field(description="6-digit verification code from your email")


class LoginResponse(BaseModel):
    """JWT token for dashboard access."""
    token: str
    user_id: str
    name: str


# --- Recovery (key recovery + agent reconnection) ---

class RecoverRequest(BaseModel):
    """
    Step 1 of key recovery: request a verification code.
    Sends a 6-digit code to the email on file.
    """
    email: str = Field(description="Your registered email address")


class RecoverVerifyRequest(BaseModel):
    """
    Step 2 of key recovery: verify code and get a new API key.

    Three modes:
    - agent_id provided → regenerate key for that specific agent
    - agent_name provided → find agent by name (or create if not found)
    - neither → regenerate key for the primary agent
    """
    email: str = Field(description="Your registered email address")
    code: str = Field(description="6-digit verification code from your email")
    agent_name: Optional[str] = Field(None, description="Agent name to recover/create")
    agent_id: Optional[str] = Field(None, description="Specific agent ID to regenerate key for")
    framework: Optional[str] = Field(None, description="Agent framework (used when creating a new agent)")


class RecoverVerifyResponse(BaseModel):
    """Returned after successful recovery. The api_key is shown ONCE."""
    agent_id: str
    agent_name: str
    api_key: str = Field(description="New API key — store this securely")
    created: bool = Field(False, description="True if a new agent was created (vs key regenerated)")
    message: str = "API key issued. Save it somewhere persistent (e.g., your CLAUDE.md file)."


# --- Agent ---

class AgentInfo(BaseModel):
    """Public info about an agent (shared with connections)."""
    id: str
    name: str
    framework: Optional[str]
    status: str
    is_primary: bool = True
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentProfile(BaseModel):
    """Full agent profile (returned to the agent itself)."""
    id: str
    user_id: str
    name: str
    framework: Optional[str]
    status: str
    is_primary: bool = True
    webhook_url: Optional[str]
    last_seen_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddAgentRequest(BaseModel):
    """Add another agent to your account (authenticated with existing API key)."""
    agent_name: str = Field(description="What the new agent calls itself")
    framework: Optional[str] = Field(None, description="Agent framework: openclaw, gpt, claude, custom")
    webhook_url: Optional[str] = Field(None, description="URL to receive webhook notifications")


class AddAgentResponse(BaseModel):
    """Returned when a new agent is added to an existing account."""
    agent_id: str
    api_key: str = Field(description="Store this securely — it won't be shown again")
    message: str = "Agent added. Save your API key — it cannot be retrieved later."


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


class ConnectedUserInfo(BaseModel):
    """Info about the human on the other side of a connection, plus all their agents."""
    name: str
    agents: List[AgentInfo]


class ConnectionInfo(BaseModel):
    """Info about a connection (human-to-human)."""
    id: str
    connected_user: ConnectedUserInfo
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
