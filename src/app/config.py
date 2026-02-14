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
