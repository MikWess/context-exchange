"""
Observer page — a simple HTML view for humans to watch agent conversations.

GET /observe?token=YOUR_API_KEY  → Live activity feed showing all your
                                    threads and messages, auto-refreshes
                                    every 10 seconds.

This is the "debug mode" — lets you see exactly what your agent is saying
to other agents and what they're saying back.
"""
from datetime import datetime
from html import escape as html_escape

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import verify_api_key, API_KEY_PREFIX
from src.app.database import get_db
from src.app.models import Agent, Connection, Thread, Message

router = APIRouter(tags=["observe"])


async def _get_agent_by_token(token: str, db: AsyncSession) -> Agent:
    """Look up an agent by raw API key (passed as query param)."""
    if not token.startswith(API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    for agent in agents:
        if verify_api_key(token, agent.api_key_hash):
            return agent

    raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/observe", response_class=HTMLResponse)
async def observe_feed(
    token: str = Query(..., description="Your API key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Renders a simple HTML page showing all your agent's conversations.
    Auto-refreshes every 10 seconds so you can watch in real time.

    Input: API key as ?token= query param
    Output: HTML page with all threads and messages
    """
    # Authenticate via query param
    agent = await _get_agent_by_token(token, db)

    # Load the agent's user name
    from src.app.models import User
    result = await db.execute(select(User).where(User.id == agent.user_id))
    user = result.scalar_one()

    # Get all connections
    result = await db.execute(
        select(Connection).where(
            Connection.status == "active",
            or_(
                Connection.agent_a_id == agent.id,
                Connection.agent_b_id == agent.id,
            ),
        )
    )
    connections = result.scalars().all()

    # Build a map of agent IDs to names (for display)
    agent_ids = set()
    for conn in connections:
        agent_ids.add(conn.agent_a_id)
        agent_ids.add(conn.agent_b_id)
    agent_ids.add(agent.id)

    agent_names = {}
    if agent_ids:
        result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        for a in result.scalars().all():
            agent_names[a.id] = a.name

    # Get all threads for these connections
    connection_ids = [c.id for c in connections]
    threads_with_messages = []

    if connection_ids:
        result = await db.execute(
            select(Thread)
            .where(Thread.connection_id.in_(connection_ids))
            .order_by(desc(Thread.last_message_at))
        )
        threads = result.scalars().all()

        for thread in threads:
            # Get messages for this thread (most recent 50)
            result = await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id)
                .order_by(Message.created_at)
                .limit(50)
            )
            messages = result.scalars().all()
            threads_with_messages.append((thread, messages))

    # Build the HTML
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Build threads HTML
    threads_html = ""
    if not threads_with_messages:
        threads_html = '<p style="color: #888; text-align: center; padding: 40px;">No conversations yet. Once your agent starts talking, messages will show up here.</p>'
    else:
        for thread, messages in threads_with_messages:
            subject = html_escape(thread.subject or "Untitled thread")
            threads_html += f'<div class="thread"><div class="thread-header">{subject}</div>'

            for msg in messages:
                sender = html_escape(agent_names.get(msg.from_agent_id, msg.from_agent_id))
                receiver = html_escape(agent_names.get(msg.to_agent_id, msg.to_agent_id))
                content = html_escape(msg.content)
                category = html_escape(msg.category) if msg.category else ""
                time_str = msg.created_at.strftime("%H:%M")
                is_mine = msg.from_agent_id == agent.id

                # Status indicator
                status_icon = {"sent": "○", "delivered": "◑", "read": "●"}.get(msg.status, "?")

                bubble_class = "msg-mine" if is_mine else "msg-theirs"
                threads_html += f'''
                <div class="msg {bubble_class}">
                    <div class="msg-header">
                        <span class="msg-sender">{sender} → {receiver}</span>
                        <span class="msg-time">{time_str} {status_icon}</span>
                    </div>
                    <div class="msg-content">{content}</div>
                    <div class="msg-meta">{html_escape(msg.message_type)}{(' · ' + category) if category else ''}</div>
                </div>'''

            threads_html += '</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>BotJoin — Observer</title>
    <meta http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
            max-width: 800px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .subtitle {{
            color: #888;
            font-size: 13px;
            margin-bottom: 24px;
        }}
        .status-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 14px;
            background: #151515;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 13px;
        }}
        .status-dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #22c55e;
            margin-right: 6px;
        }}
        .thread {{
            background: #151515;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        .thread-header {{
            font-weight: 600;
            font-size: 14px;
            color: #aaa;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #252525;
        }}
        .msg {{
            padding: 10px 14px;
            margin-bottom: 8px;
            border-radius: 8px;
            font-size: 14px;
        }}
        .msg-mine {{
            background: #1a2a1a;
            border-left: 3px solid #22c55e;
        }}
        .msg-theirs {{
            background: #1a1a2a;
            border-left: 3px solid #6366f1;
        }}
        .msg-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .msg-sender {{
            font-size: 12px;
            font-weight: 600;
            color: #888;
        }}
        .msg-time {{
            font-size: 12px;
            color: #666;
        }}
        .msg-content {{
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .msg-meta {{
            font-size: 11px;
            color: #555;
            margin-top: 6px;
        }}
        .legend {{
            font-size: 12px;
            color: #555;
            text-align: center;
            margin-top: 16px;
        }}
    </style>
</head>
<body>
    <h1>BotJoin — Observer</h1>
    <p class="subtitle">Watching {agent.name}'s conversations</p>

    <div class="status-bar">
        <span><span class="status-dot"></span> {user.name} ({agent.name})</span>
        <span>{len(connections)} connection{'s' if len(connections) != 1 else ''} · {now}</span>
    </div>

    {threads_html}

    <p class="legend">○ sent · ◑ delivered · ● read — auto-refreshes every 10s</p>
</body>
</html>"""

    return HTMLResponse(content=html)
