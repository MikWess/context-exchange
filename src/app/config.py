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

# Permission system — 3 categories of context agents can share.
# When two agents connect, permissions are set by a "contract" preset.
DEFAULT_CATEGORIES = ["info", "requests", "personal"]
VALID_PERMISSION_LEVELS = {"auto", "ask", "never"}

# Contracts — named permission presets applied at connection time.
# Each contract maps category -> level. Both agents get the same preset.
# "friends" is the default — agents can exchange info autonomously right away.
BUILT_IN_CONTRACTS = {
    "friends": {"info": "auto", "requests": "ask", "personal": "ask"},
    "coworkers": {"info": "auto", "requests": "auto", "personal": "never"},
    "casual": {"info": "auto", "requests": "never", "personal": "never"},
}
DEFAULT_CONTRACT = "friends"

# Platform version — bumped when onboarding instructions change significantly.
# Agents compare this against their cached version to know when to re-fetch /setup.
INSTRUCTIONS_VERSION = "4"

# --- Email Verification ---
# Verification codes expire after this many minutes
EMAIL_VERIFICATION_EXPIRE_MINUTES = int(os.getenv("EMAIL_VERIFICATION_EXPIRE_MINUTES", "10"))

# Resend API key for sending verification emails.
# In dev/test, if not set, emails are skipped and the code is returned directly.
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

# The "from" address for verification emails (must be verified in Resend)
EMAIL_FROM = os.getenv("EMAIL_FROM", "BotJoin <noreply@botjoin.ai>")

# Admin key for platform management (creating announcements, etc.)
# Set via environment variable in production.
ADMIN_KEY = os.getenv("ADMIN_KEY", "dev-admin-key")
