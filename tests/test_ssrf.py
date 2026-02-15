"""
Tests for SSRF protection on webhook URLs.

Covers:
- HTTPS required (http:// rejected)
- Localhost blocked (127.0.0.1, localhost, ::1, 0.0.0.0)
- Private IPs blocked (10.x, 172.16.x, 192.168.x)
- Link-local IPs blocked (169.254.x — AWS metadata attack vector)
- Valid HTTPS URLs accepted
- SSRF checks apply to both registration and PUT /auth/me
"""
import pytest

from tests.conftest import auth_header


# --- Registration with bad webhook URLs ---

@pytest.mark.asyncio
async def test_register_rejects_http_webhook(client):
    """Webhook URL must be HTTPS — plain HTTP is rejected."""
    resp = await client.post("/auth/register", json={
        "email": "http@test.com",
        "name": "HTTP User",
        "agent_name": "HTTP Agent",
        "framework": "custom",
        "webhook_url": "http://example.com/webhook",
    })
    assert resp.status_code == 400
    assert "HTTPS" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_rejects_localhost_webhook(client):
    """Webhook URL cannot point to localhost."""
    resp = await client.post("/auth/register", json={
        "email": "local@test.com",
        "name": "Local User",
        "agent_name": "Local Agent",
        "framework": "custom",
        "webhook_url": "https://localhost/webhook",
    })
    assert resp.status_code == 400
    assert "localhost" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_rejects_127_webhook(client):
    """Webhook URL cannot point to 127.0.0.1."""
    resp = await client.post("/auth/register", json={
        "email": "loopback@test.com",
        "name": "Loopback User",
        "agent_name": "Loopback Agent",
        "framework": "custom",
        "webhook_url": "https://127.0.0.1/webhook",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_rejects_private_ip_webhook(client):
    """Webhook URL cannot point to private IP ranges (10.x, 192.168.x, etc.)."""
    private_ips = [
        "https://10.0.0.1/webhook",
        "https://192.168.1.1/webhook",
        "https://172.16.0.1/webhook",
    ]
    for url in private_ips:
        resp = await client.post("/auth/register", json={
            "email": f"priv-{url.split('//')[1].split('/')[0]}@test.com",
            "name": "Priv User",
            "agent_name": "Priv Agent",
            "framework": "custom",
            "webhook_url": url,
        })
        assert resp.status_code == 400, f"Expected 400 for {url}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_register_rejects_link_local_webhook(client):
    """Webhook URL cannot point to link-local IPs (169.254.x — AWS metadata attack)."""
    resp = await client.post("/auth/register", json={
        "email": "linklocal@test.com",
        "name": "Link Local User",
        "agent_name": "Link Local Agent",
        "framework": "custom",
        "webhook_url": "https://169.254.169.254/latest/meta-data/",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_accepts_valid_https_webhook(client):
    """Valid HTTPS URL with a public hostname is accepted."""
    resp = await client.post("/auth/register", json={
        "email": "valid@test.com",
        "name": "Valid User",
        "agent_name": "Valid Agent",
        "framework": "custom",
        "webhook_url": "https://my-agent-server.example.com/webhook",
    })
    assert resp.status_code == 200


# --- PUT /auth/me with bad webhook URLs ---

@pytest.mark.asyncio
async def test_update_rejects_http_webhook(client, registered_agent):
    """PUT /auth/me also validates webhook URLs — rejects HTTP."""
    resp = await client.put(
        "/auth/me",
        json={"webhook_url": "http://evil.com/steal-data"},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 400
    assert "HTTPS" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_rejects_private_ip_webhook(client, registered_agent):
    """PUT /auth/me rejects private IPs."""
    resp = await client.put(
        "/auth/me",
        json={"webhook_url": "https://10.0.0.1/internal"},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_accepts_valid_https_webhook(client, registered_agent):
    """PUT /auth/me accepts valid HTTPS URLs."""
    resp = await client.put(
        "/auth/me",
        json={"webhook_url": "https://my-server.example.com/hook"},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["webhook_url"] == "https://my-server.example.com/hook"
