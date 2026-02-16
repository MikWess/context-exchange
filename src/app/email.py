"""
Email sending utility for verification codes.

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
            if resp.status_code == 200:
                logger.info(f"Verification email sent to {to_email}")
                return True
            else:
                logger.error(f"Resend API error: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        return False
