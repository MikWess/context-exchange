"""
Application configuration.
Reads from environment variables with sensible defaults for local dev.
"""
import os
import secrets


# Database — SQLite for dev, swap to Postgres URL for prod
# Railway provides DATABASE_URL as "postgresql://..." but async SQLAlchemy
# needs "postgresql+asyncpg://..." — we auto-convert here.
_raw_db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./context_exchange.db")
if _raw_db_url.startswith("postgresql://"):
    DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgres://"):
    DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_db_url

# JWT secret for dashboard auth (human login)
# In prod, set this to a stable secret. In dev, generates a random one per run.
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# API key prefix — makes it easy to identify Context Exchange keys in logs
API_KEY_PREFIX = "cex_"

# Invite codes expire after this many hours
INVITE_EXPIRE_HOURS = int(os.getenv("INVITE_EXPIRE_HOURS", "72"))

# Permission system — categories of context agents can share
# When two agents connect, one Permission row is created per category per agent.
DEFAULT_CATEGORIES = ["schedule", "projects", "knowledge", "interests", "requests", "personal"]
DEFAULT_PERMISSION_LEVEL = "ask"  # auto = share freely, ask = check with human, never = blocked
VALID_PERMISSION_LEVELS = {"auto", "ask", "never"}

# Inbound defaults — what the agent accepts FROM other agents, per category.
# Safe categories (schedule, projects, etc.) default to "auto" (accept freely).
# Sensitive categories (requests, personal) default to "ask" (check with human first).
DEFAULT_INBOUND_LEVELS = {
    "schedule": "auto",
    "projects": "auto",
    "knowledge": "auto",
    "interests": "auto",
    "requests": "ask",
    "personal": "ask",
}

# Platform version — bumped when onboarding instructions change significantly.
# Agents compare this against their cached version to know when to re-fetch /setup.
INSTRUCTIONS_VERSION = "3"

# Admin key for platform management (creating announcements, etc.)
# Set via environment variable in production.
ADMIN_KEY = os.getenv("ADMIN_KEY", "dev-admin-key")
