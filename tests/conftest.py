"""
Shared test fixtures.

Uses an in-memory SQLite database so tests are fast and isolated.
Every test gets a fresh database.
"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.app.database import Base, get_db
from src.app.main import app


# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture
def event_loop():
    """Use a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def client(db_session):
    """
    HTTP test client with the database overridden to use our test DB.
    """
    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _register_and_verify(client, email, name, agent_name, framework):
    """
    Helper: go through the 2-step registration flow (register → verify).
    In test mode (no RESEND_API_KEY), the verification code is in the response message.
    Returns the verify response JSON (user_id, agent_id, api_key).
    """
    # Step 1: Register — get the verification code from the dev-mode message
    reg_resp = await client.post("/auth/register", json={
        "email": email,
        "name": name,
    })
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    # Dev mode message format: "Dev mode — your verification code is: 123456. ..."
    code = reg_data["message"].split("code is: ")[1].split(".")[0]

    # Step 2: Verify — creates the agent and returns the API key
    verify_resp = await client.post("/auth/verify", json={
        "email": email,
        "code": code,
        "agent_name": agent_name,
        "framework": framework,
    })
    assert verify_resp.status_code == 200
    return verify_resp.json()


@pytest.fixture
async def registered_agent(client):
    """
    Register a user + agent via the 2-step flow and return the response.
    Includes the raw API key for use in subsequent requests.
    """
    return await _register_and_verify(
        client, "mikey@test.com", "Mikey", "Mikey's Agent", "openclaw",
    )


@pytest.fixture
async def second_agent(client):
    """Register a second agent for connection/messaging tests."""
    return await _register_and_verify(
        client, "sam@test.com", "Sam", "Sam's Agent", "gpt",
    )


def auth_header(api_key: str) -> dict:
    """Helper to build the Authorization header."""
    return {"Authorization": f"Bearer {api_key}"}
