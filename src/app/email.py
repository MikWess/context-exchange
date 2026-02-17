"""
Email sending utility for verification codes and welcome emails.

Uses Resend (https://resend.com) for sending emails.
In dev/test mode (no RESEND_API_KEY), emails are skipped — the code is
returned directly in the response so agents can auto-verify.
"""
import logging
import random
import string

import httpx

from src.app.config import IS_PRODUCTION, RESEND_API_KEY, EMAIL_FROM

logger = logging.getLogger(__name__)


def is_dev_mode() -> bool:
    """
    True when running locally (SQLite, no Resend key).
    In dev mode, verification codes are returned in responses so you
    can test without real email. NEVER true in production — even if
    RESEND_API_KEY is missing, codes stay hidden.
    """
    return not IS_PRODUCTION and not RESEND_API_KEY


def generate_verification_code() -> str:
    """Generate a random 6-digit numeric code."""
    return "".join(random.choices(string.digits, k=6))


async def send_verification_email(to_email: str, code: str) -> bool:
    """
    Send a verification code email via Resend.

    Input: recipient email + 6-digit code
    Output: True if sent (or dev mode), False if sending failed

    In dev/test mode (no RESEND_API_KEY set), skips sending and returns True.
    The caller handles returning the code directly to the agent in dev mode.
    """
    if not RESEND_API_KEY:
        logger.info(f"Dev mode: skipping email to {to_email}, code is {code}")
        return True

    logger.info(f"Sending verification email to {to_email} from {EMAIL_FROM}")

    # Send via Resend API — one simple HTTP POST
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": EMAIL_FROM,
                    "to": [to_email],
                    "subject": "BotJoin — Your verification code",
                    "html": (
                        f"<h2>Your BotJoin verification code</h2>"
                        f"<p style='font-size: 32px; font-weight: bold; "
                        f"letter-spacing: 8px; font-family: monospace;'>{code}</p>"
                        f"<p>This code expires in 10 minutes.</p>"
                        f"<p>If you didn't register on BotJoin, ignore this email.</p>"
                    ),
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201, 202):
                logger.info(f"Verification email sent to {to_email}")
                return True
            else:
                logger.error(f"Resend API error: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        return False


def get_base_url(request) -> str:
    """
    Extract the base URL from a FastAPI Request, respecting X-Forwarded-Proto.

    Railway (and most cloud hosts) terminate HTTPS at their load balancer
    and forward http:// to the app. This mirrors the pattern in onboard.py.
    """
    base_url = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https":
        base_url = base_url.replace("http://", "https://", 1)
    return base_url


def _welcome_email_html(
    user_name: str,
    base_url: str,
    agent_name: str | None = None,
) -> tuple[str, str]:
    """
    Build welcome email subject + HTML body.

    Two variants:
    - agent_name provided (agent flow): mentions the agent, links to /observe
    - agent_name is None (UI flow): mentions account only, links to /setup
    """
    if agent_name:
        subject = f"Welcome to BotJoin — {agent_name} is ready"
        html = (
            f"<h2>Welcome to BotJoin, {user_name}!</h2>"
            f"<p>Your agent <strong>{agent_name}</strong> has been created "
            f"and is ready to go.</p>"
            f"<p>You can watch your agent's conversations anytime on your dashboard:</p>"
            f'<p><a href="{base_url}/observe">{base_url}/observe</a></p>'
            f"<p>Log in with your email — no password needed.</p>"
            f"<p style='color: #6b7280; font-size: 13px; margin-top: 24px;'>"
            f"If you didn't create this account, you can ignore this email.</p>"
        )
    else:
        subject = "Welcome to BotJoin — your account is ready"
        html = (
            f"<h2>Welcome to BotJoin, {user_name}!</h2>"
            f"<p>Your account is set up. Now connect your first AI agent:</p>"
            f'<p><a href="{base_url}/setup">{base_url}/setup</a></p>'
            f"<p>Just give that link to your AI agent and it will handle the rest.</p>"
            f"<p style='color: #6b7280; font-size: 13px; margin-top: 24px;'>"
            f"If you didn't create this account, you can ignore this email.</p>"
        )
    return subject, html


async def send_welcome_email(
    to_email: str,
    user_name: str,
    base_url: str,
    agent_name: str | None = None,
) -> bool:
    """
    Send a welcome email after first-time verification.

    Fire-and-forget — callers should not raise on failure.
    In dev mode, skips sending and returns True.
    """
    if not RESEND_API_KEY:
        logger.info(f"Dev mode: skipping welcome email to {to_email}")
        return True

    subject, html = _welcome_email_html(user_name, base_url, agent_name)

    logger.info(f"Sending welcome email to {to_email}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": EMAIL_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201, 202):
                logger.info(f"Welcome email sent to {to_email}")
                return True
            else:
                logger.error(f"Resend API error (welcome): {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send welcome email: {e}")
        return False
