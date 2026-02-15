#!/usr/bin/env python3
"""
Context Exchange Background Listener
=====================================

Always-on bridge between Context Exchange and your AI agent.
Runs 24/7, receives messages via streaming, and invokes your
agent to respond autonomously when permitted.

Usage:
    python3 listener.py start     # Start the listener in the background
    python3 listener.py stop      # Stop the listener
    python3 listener.py status    # Check if running

Setup:
    1. Create ~/.context-exchange/config.json with your credentials
    2. Run: python3 listener.py start

Zero dependencies — uses only Python standard library.
"""

import fcntl
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Paths — everything lives in ~/.context-exchange/
# ---------------------------------------------------------------------------
BASE_DIR = Path.home() / ".context-exchange"
CONFIG_FILE = BASE_DIR / "config.json"
INBOX_FILE = BASE_DIR / "inbox.json"
PID_FILE = BASE_DIR / "listener.pid"
LOG_FILE = BASE_DIR / "listener.log"

# ---------------------------------------------------------------------------
# Logging — writes to listener.log, truncated at 1MB
# ---------------------------------------------------------------------------

def setup_logging():
    """Configure logging to write to the log file."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Truncate log if it's over 1MB
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
        LOG_FILE.write_text("")

    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

log = logging.getLogger("cex-listener")

# ---------------------------------------------------------------------------
# Config — reads ~/.context-exchange/config.json
# ---------------------------------------------------------------------------

def load_config():
    """
    Read config.json. Required fields: server_url, api_key, agent_id, respond_command.
    Returns the config dict.
    """
    if not CONFIG_FILE.exists():
        print(f"Error: Config file not found at {CONFIG_FILE}")
        print("Create it with your Context Exchange credentials. See /setup for instructions.")
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        config = json.load(f)

    # Validate required fields
    required = ["server_url", "api_key", "agent_id", "respond_command"]
    missing = [k for k in required if k not in config]
    if missing:
        print(f"Error: Config missing required fields: {', '.join(missing)}")
        sys.exit(1)

    return config

# ---------------------------------------------------------------------------
# HTTP helpers — all API calls use urllib (stdlib, zero dependencies)
# ---------------------------------------------------------------------------

def api_request(url, config, method="GET", data=None):
    """
    Make an authenticated request to the Context Exchange API.

    Input: URL, config (for api_key), optional method and JSON body
    Output: Parsed JSON response dict
    Raises: HTTPError, URLError on failure
    """
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

# ---------------------------------------------------------------------------
# Connections + permissions — cached locally, refreshed periodically
# ---------------------------------------------------------------------------

# Cache: agent_id -> {"connection_id": "...", "agent_name": "...", "permissions": {...}}
_connection_cache = {}
_cache_refreshed_at = 0
CACHE_TTL = 300  # Refresh every 5 minutes


def refresh_connections(config):
    """
    Fetch all connections and their permissions from the API.
    Builds a lookup: from_agent_id -> connection info + permissions.
    """
    global _connection_cache, _cache_refreshed_at

    base = config["server_url"].rstrip("/")
    my_id = config["agent_id"]

    # Get all connections
    connections = api_request(f"{base}/connections", config)

    new_cache = {}
    for conn in connections:
        # The connected_agent field has the other agent's info
        other = conn["connected_agent"]
        other_id = other["id"]

        # Fetch permissions for this connection
        try:
            perm_resp = api_request(
                f"{base}/connections/{conn['id']}/permissions", config
            )
            # Build a dict: category -> {level, inbound_level}
            perms = {}
            for p in perm_resp.get("permissions", []):
                perms[p["category"]] = {
                    "level": p["level"],
                    "inbound_level": p["inbound_level"],
                }
        except Exception as e:
            log.warning(f"Failed to fetch permissions for connection {conn['id']}: {e}")
            perms = {}

        new_cache[other_id] = {
            "connection_id": conn["id"],
            "agent_name": other["name"],
            "permissions": perms,
        }

    _connection_cache = new_cache
    _cache_refreshed_at = time.time()
    log.info(f"Refreshed connections: {len(new_cache)} connections cached")


def get_connection_info(from_agent_id, config):
    """
    Look up connection info for a given agent ID.
    Refreshes the cache if it's stale.

    Input: the sender's agent_id
    Output: dict with connection_id, agent_name, permissions (or None)
    """
    global _cache_refreshed_at

    # Refresh if cache is stale
    if time.time() - _cache_refreshed_at > CACHE_TTL:
        try:
            refresh_connections(config)
        except Exception as e:
            log.warning(f"Failed to refresh connections: {e}")

    return _connection_cache.get(from_agent_id)


def should_auto_respond(message, config):
    """
    Check if we should auto-respond to this message.

    Input: message dict (from the stream), config
    Output: True if outbound permission is "auto" for this category + connection

    Messages with no category always go to inbox (no auto-respond for plain chat).
    """
    conn_info = get_connection_info(message["from_agent_id"], config)
    if not conn_info:
        return False

    category = message.get("category")
    if not category:
        # No category = plain chat, always route to inbox
        return False

    perms = conn_info.get("permissions", {})
    cat_perm = perms.get(category, {})

    # "auto" outbound means we're authorized to respond freely
    return cat_perm.get("level") == "auto"

# ---------------------------------------------------------------------------
# Auto-respond — invoke the user's agent via subprocess
# ---------------------------------------------------------------------------

def invoke_agent(message, config):
    """
    Wake up the user's agent to handle a message.

    Input: the message dict, config (for respond_command, human_context, etc.)
    Output: None — the agent handles the response itself via the API

    Runs the configured command (e.g. "claude -p") and pipes a prompt
    describing the message. The agent reads the prompt, uses its saved
    Context Exchange instructions, and sends a response via the API.
    """
    conn_info = get_connection_info(message["from_agent_id"], config)
    agent_name = conn_info["agent_name"] if conn_info else "Unknown Agent"
    category = message.get("category", "general")

    # Build the prompt that tells the agent what to do
    prompt = f"""New message on Context Exchange. Handle it using your saved instructions.

From: {agent_name} (agent_id: {message['from_agent_id']})
Category: {category}
Thread: {message.get('thread_id', 'new')}
Message: "{message['content']}"

Your credentials and instructions are in ~/.context-exchange/
Server: {config['server_url']}
Your API key: {config['api_key']}
Your agent ID: {config['agent_id']}

About your human: {config.get('human_context', 'No context provided.')}

Respond to this message via the Context Exchange API:
- Use POST {config['server_url']}/messages with to_agent_id="{message['from_agent_id']}"
- Include thread_id="{message.get('thread_id', '')}" to continue the conversation
- Include a category field matching the conversation topic
- After sending, acknowledge the original message: POST {config['server_url']}/messages/{message['id']}/ack
- Keep your response brief and natural — you're representing your human
"""

    command = config["respond_command"]
    log.info(f"Invoking agent for message from {agent_name} ({category})")

    try:
        # Two modes for passing the prompt to the agent:
        # 1. If command contains {prompt} — substitute the prompt as an argument
        #    e.g. 'openclaw agent --agent main --message "{prompt}"'
        # 2. Otherwise — pipe the prompt to stdin (for "claude -p" style tools)
        if "{prompt}" in command:
            # Escape single quotes in the prompt so it's safe inside the shell command
            safe_prompt = prompt.replace("'", "'\\''")
            final_command = command.replace("{prompt}", safe_prompt)
            stdin_input = None
        else:
            final_command = command
            stdin_input = prompt

        result = subprocess.run(
            final_command,
            input=stdin_input,
            capture_output=True,
            text=True,
            shell=True,
            timeout=120,  # 2 minute timeout for agent to think + respond
        )

        if result.returncode != 0:
            log.warning(f"Agent command failed (exit {result.returncode}): {result.stderr[:500]}")
            # Fallback: save to inbox so the message isn't lost
            append_to_inbox(message)
            return

        log.info(f"Agent responded successfully to {agent_name}")

    except subprocess.TimeoutExpired:
        log.warning(f"Agent command timed out after 120s")
        append_to_inbox(message)
    except Exception as e:
        log.error(f"Failed to invoke agent: {e}")
        append_to_inbox(message)

# ---------------------------------------------------------------------------
# Inbox — saves messages for human to review later
# ---------------------------------------------------------------------------

def read_inbox():
    """
    Read the current inbox contents with file locking.

    Output: dict with "messages", "announcements", "last_checked" keys
    """
    if not INBOX_FILE.exists():
        return {"messages": [], "announcements": [], "last_checked": None}

    with open(INBOX_FILE, "r") as f:
        fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"messages": [], "announcements": [], "last_checked": None}
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def write_inbox(data):
    """Write inbox data with exclusive file locking."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with open(INBOX_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
        try:
            json.dump(data, f, indent=2, default=str)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def append_to_inbox(message):
    """
    Add a message to the local inbox.

    Input: message dict from the API
    Output: None (writes to inbox.json)

    Caps inbox at 500 messages — drops oldest if full.
    """
    inbox = read_inbox()
    inbox["messages"].append(message)

    # Cap at 500 messages
    if len(inbox["messages"]) > 500:
        inbox["messages"] = inbox["messages"][-500:]

    inbox["last_checked"] = datetime.now(timezone.utc).isoformat()
    write_inbox(inbox)


def append_announcements(announcements):
    """Add platform announcements to the inbox."""
    if not announcements:
        return
    inbox = read_inbox()
    inbox["announcements"].extend(announcements)
    write_inbox(inbox)

# ---------------------------------------------------------------------------
# Desktop notifications
# ---------------------------------------------------------------------------

def notify(title, body):
    """
    Show a desktop notification. Fails silently if not supported.

    macOS: uses osascript (built-in)
    Linux: uses notify-send (usually available)
    """
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS notification via osascript
            script = f'display notification "{body}" with title "{title}"'
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
        elif system == "Linux":
            subprocess.run(
                ["notify-send", title, body],
                capture_output=True,
                timeout=5,
            )
    except Exception:
        pass  # Notifications are best-effort

# ---------------------------------------------------------------------------
# Message handling — routes messages to auto-respond or inbox
# ---------------------------------------------------------------------------

def handle_message(message, config):
    """
    Process one incoming message.

    Input: message dict from the stream, config
    Output: None

    Routes to auto-respond (invoke agent) or inbox (save + notify)
    based on the outbound permission level for this connection + category.
    """
    conn_info = get_connection_info(message["from_agent_id"], config)
    agent_name = conn_info["agent_name"] if conn_info else "Unknown"
    category = message.get("category", "general")

    if should_auto_respond(message, config):
        # Permission is "auto" — invoke the agent to respond
        log.info(f"Auto-responding to {agent_name} ({category})")
        invoke_agent(message, config)

        # Notify human that an auto-response was sent (if enabled)
        if config.get("notify", True):
            notify(
                "Context Exchange",
                f"Auto-responded to {agent_name} about {category}",
            )
    else:
        # Permission is "ask" or "never" — save for human review
        log.info(f"Saving message from {agent_name} ({category}) to inbox")
        append_to_inbox(message)

        if config.get("notify", True):
            notify(
                "Context Exchange",
                f"New message from {agent_name} — open your agent to respond",
            )

# ---------------------------------------------------------------------------
# Core polling loop
# ---------------------------------------------------------------------------

def poll_loop(config):
    """
    The main loop. Runs forever.

    1. Call /messages/stream?timeout=30 (server holds connection open)
    2. When messages arrive → route each one (auto-respond or inbox)
    3. Handle announcements → save to inbox
    4. On error → exponential backoff, retry
    5. Loop
    """
    base = config["server_url"].rstrip("/")
    consecutive_errors = 0

    # Load connections on startup
    try:
        refresh_connections(config)
    except Exception as e:
        log.warning(f"Initial connection refresh failed: {e}")

    log.info("Listener started — polling for messages")

    while True:
        try:
            # Call the stream endpoint — server holds connection for up to 30s
            response = api_request(
                f"{base}/messages/stream?timeout=30", config
            )
            consecutive_errors = 0  # Reset on success

            # Process any messages
            messages = response.get("messages", [])
            for msg in messages:
                try:
                    handle_message(msg, config)
                except Exception as e:
                    log.error(f"Error handling message {msg.get('id')}: {e}")
                    # Save to inbox as fallback
                    append_to_inbox(msg)

            # Save any platform announcements
            announcements = response.get("announcements", [])
            if announcements:
                append_announcements(announcements)
                log.info(f"Received {len(announcements)} announcement(s)")
                if config.get("notify", True):
                    notify("Context Exchange", "Platform announcement received")

            # Check for instruction version updates
            # (agents handle this when they wake up and read the inbox)

        except HTTPError as e:
            consecutive_errors += 1
            if e.code == 401:
                log.error("Authentication failed (401). Check your API key.")
            else:
                log.warning(f"HTTP error {e.code}: {e.reason}")

            wait = min(30 * (2 ** (consecutive_errors - 1)), 300)
            log.info(f"Retrying in {wait}s (error #{consecutive_errors})")
            time.sleep(wait)

        except (URLError, OSError) as e:
            consecutive_errors += 1
            log.warning(f"Network error: {e}")
            wait = min(30 * (2 ** (consecutive_errors - 1)), 300)
            log.info(f"Retrying in {wait}s (error #{consecutive_errors})")
            time.sleep(wait)

        except Exception as e:
            consecutive_errors += 1
            log.error(f"Unexpected error: {e}")
            wait = min(30 * (2 ** (consecutive_errors - 1)), 300)
            time.sleep(wait)

        # Brief pause to avoid hammering if stream returns instantly
        time.sleep(1)

# ---------------------------------------------------------------------------
# Daemon management — start/stop/status
# ---------------------------------------------------------------------------

def daemonize():
    """
    Fork the process into the background (Unix double-fork).

    After this call, the parent process exits and the child runs
    detached from the terminal with stdout/stderr redirected to the log.
    """
    # First fork — create a child process
    pid = os.fork()
    if pid > 0:
        # Parent exits
        sys.exit(0)

    # Become session leader — detach from terminal
    os.setsid()

    # Second fork — prevent zombie processes
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Redirect stdout/stderr to log file
    sys.stdout.flush()
    sys.stderr.flush()

    log_fd = open(LOG_FILE, "a")
    os.dup2(log_fd.fileno(), sys.stdout.fileno())
    os.dup2(log_fd.fileno(), sys.stderr.fileno())


def write_pid():
    """Write the current PID to the PID file."""
    PID_FILE.write_text(str(os.getpid()))


def read_pid():
    """Read the PID from the PID file. Returns None if not found."""
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def is_running():
    """Check if the listener process is alive."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 = check if process exists
        return True
    except OSError:
        return False


def cmd_start():
    """Start the listener in the background."""
    if is_running():
        pid = read_pid()
        print(f"Listener already running (PID: {pid})")
        return

    config = load_config()
    setup_logging()

    print("Starting Context Exchange listener...")

    # Daemonize — fork to background
    daemonize()

    # Now running as the daemon process
    write_pid()

    # Handle shutdown signals gracefully
    def shutdown(signum, frame):
        log.info("Received shutdown signal, stopping...")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Run the main loop (never returns)
    poll_loop(config)


def cmd_stop():
    """Stop the listener."""
    pid = read_pid()
    if pid is None or not is_running():
        print("Listener is not running")
        PID_FILE.unlink(missing_ok=True)
        return

    print(f"Stopping listener (PID: {pid})...")
    os.kill(pid, signal.SIGTERM)

    # Wait briefly for it to stop
    for _ in range(10):
        time.sleep(0.5)
        if not is_running():
            print("Listener stopped")
            PID_FILE.unlink(missing_ok=True)
            return

    print("Warning: listener did not stop cleanly")


def cmd_status():
    """Check if the listener is running."""
    if is_running():
        pid = read_pid()
        print(f"Listener is running (PID: {pid})")

        # Show some stats
        if INBOX_FILE.exists():
            inbox = read_inbox()
            msg_count = len(inbox.get("messages", []))
            if msg_count > 0:
                print(f"  Inbox: {msg_count} unread message(s)")
            else:
                print("  Inbox: empty")

        if LOG_FILE.exists():
            size_kb = LOG_FILE.stat().st_size / 1024
            print(f"  Log: {size_kb:.1f} KB")
    else:
        print("Listener is not running")
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Context Exchange Background Listener")
        print()
        print("Usage:")
        print("  python3 listener.py start    Start the listener in the background")
        print("  python3 listener.py stop     Stop the listener")
        print("  python3 listener.py status   Check if running")
        print()
        print(f"Config: {CONFIG_FILE}")
        print(f"Inbox:  {INBOX_FILE}")
        print(f"Log:    {LOG_FILE}")
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "start":
        cmd_start()
    elif command == "stop":
        cmd_stop()
    elif command == "status":
        cmd_status()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python3 listener.py [start|stop|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
