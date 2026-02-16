"""
Tests for the client endpoint that serves the listener script.

Covers:
- Endpoint returns 200 with the script content
- Response is plain text
- Script contains key functions
- Instructions version bumped
"""
import pytest


@pytest.mark.asyncio
async def test_get_listener_returns_script(client):
    """GET /client/listener returns the listener script."""
    resp = await client.get("/client/listener")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_listener_is_valid_python(client):
    """The returned script is valid Python (starts with shebang or docstring)."""
    resp = await client.get("/client/listener")
    content = resp.text
    # Should start with a shebang or docstring
    assert content.startswith("#!/usr/bin/env python3") or content.startswith('"""')


@pytest.mark.asyncio
async def test_listener_contains_key_functions(client):
    """The script contains the critical functions for the listener to work."""
    resp = await client.get("/client/listener")
    content = resp.text

    # Core functions that must exist
    assert "def poll_loop(" in content
    assert "def handle_message(" in content
    assert "def invoke_agent(" in content
    assert "def append_to_inbox(" in content
    assert "def daemonize(" in content
    assert "def cmd_start(" in content
    assert "def cmd_stop(" in content
    assert "def cmd_status(" in content
    assert "def notify(" in content


@pytest.mark.asyncio
async def test_listener_has_no_dependencies(client):
    """The script uses only stdlib — no third-party imports."""
    resp = await client.get("/client/listener")
    content = resp.text

    # Should NOT import any third-party packages
    # (these are common ones that would indicate a dependency)
    assert "import requests" not in content
    assert "import httpx" not in content
    assert "import click" not in content
    assert "import typer" not in content

    # SHOULD use stdlib
    assert "from urllib.request import" in content
    assert "import subprocess" in content
    assert "import fcntl" in content


@pytest.mark.asyncio
async def test_listener_download_header(client):
    """Response includes Content-Disposition header for download."""
    resp = await client.get("/client/listener")
    assert "content-disposition" in resp.headers
    assert "listener.py" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_listener_no_auth_required(client):
    """The listener endpoint doesn't require authentication."""
    # No auth header — should still work
    resp = await client.get("/client/listener")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_instructions_version_bumped(client, registered_agent):
    """Instructions version should be '3' after adding the listener."""
    from tests.conftest import auth_header
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.json()["instructions_version"] == "4"
