"""
Application configuration.
Reads from environment variables with sensible defaults for local dev.
"""
import os
import secrets


# Database — SQLite for dev, swap to Postgres URL for prod
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./context_exchange.db")

# JWT secret for dashboard auth (human login)
# In prod, set this to a stable secret. In dev, generates a random one per run.
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# API key prefix — makes it easy to identify Context Exchange keys in logs
API_KEY_PREFIX = "cex_"

# Invite codes expire after this many hours
INVITE_EXPIRE_HOURS = int(os.getenv("INVITE_EXPIRE_HOURS", "72"))
