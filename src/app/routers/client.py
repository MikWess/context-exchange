"""
Client router — serves the listener script for download.

GET /client/listener  → Returns the background listener script as plain text.
                        No auth required — the script itself isn't sensitive.
                        The API key goes in the user's local config.json.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/client", tags=["client"])

# Path to the listener script (relative to this file)
LISTENER_PATH = Path(__file__).parent.parent / "client" / "listener.py"


@router.get("/listener", response_class=PlainTextResponse)
async def get_listener():
    """
    Download the background listener script.

    Input: Nothing (no auth required)
    Output: The listener.py script as plain text

    Agents download this during onboarding setup and run it on the
    user's machine. It streams messages 24/7 and invokes the agent
    to respond autonomously.
    """
    return PlainTextResponse(
        content=LISTENER_PATH.read_text(),
        media_type="text/plain",
        headers={
            "Content-Disposition": 'attachment; filename="listener.py"',
        },
    )
