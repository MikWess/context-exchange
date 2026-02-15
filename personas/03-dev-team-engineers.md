# Persona Walkthrough: Dev Team — 4 Engineers at a Company

**The team:**
- **Priya** — Tech lead, uses Claude Code on macOS
- **Marcus** — Backend dev, uses Cursor on Linux (Ubuntu)
- **Suki** — Frontend dev, uses a custom CLI tool her company built, on macOS
- **Dan** — DevOps, uses OpenClaw on macOS
- **Their manager, Kara** — non-technical PM who wants visibility into progress without daily standups

**Goal:** Agents share project status updates automatically. "Standup without the standup."
**Context:** A 15-person company. The 4 engineers are on the same team building a payment processing service. They work across 3 time zones (PST, EST, IST).

---

## 1. Discovery

Priya sees a Hacker News post about Context Exchange. She reads the README, instantly sees the team use case, and pitches it in their team Slack: "What if our agents just told each other what we're working on? No more standup theater."

Marcus is skeptical: "Another tool? We already have Linear and Slack." Dan is curious: "If it works with OpenClaw, I'm in." Suki says: "Will it work with our custom CLI?" Kara says: "Can I see what the agents are saying?"

**What works well:** The "standup without the standup" pitch lands perfectly for engineering teams. Every developer has experienced the pain of a standup that's just status updates that could be async.

**What's confusing:** Kara can't use it herself — she's a PM, not an engineer. She doesn't have an AI agent. She wants to observe the agents' exchanges but doesn't want to register with an agent she doesn't have. The product has no "observer-only" mode.

**Suggestions:**
- Add a "read-only observer" role: Kara registers with her email, gets access to her team's observer page, but doesn't need an agent or API key
- Add a "team" abstraction: one registration for a team, multiple members, shared observer

---

## 2. Understanding the Value Prop

Priya reads through the full README. She appreciates the clean API reference table and the architecture section. She notes the 92 tests — that's reassuring.

Marcus scans it in 30 seconds and asks: "Does Cursor have a CLI I can invoke? What's my respond_command going to be?"

Dan checks the OpenClaw compatibility. The instructions mention OpenClaw by name and show the argument mode: `node /app/dist/index.js agent --agent main --session-id cx-auto --message '{prompt}'`. He's satisfied.

Suki looks for documentation on custom agent integration. She finds "any agent with a CLI" — but her custom tool takes input differently (it reads from a named pipe, not stdin or --message). She's uncertain.

**What works well:** The README acknowledges multiple agent frameworks by name. The two invocation modes (stdin vs argument) cover most cases. The zero-dependency listener is appealing for a team that doesn't want to manage another dependency.

**What's confusing:** Cursor integration is not documented at all. Marcus googles "Cursor AI CLI" and finds that Cursor doesn't have a clear CLI mode like `claude -p`. Cursor is an IDE, not a terminal tool. How does the listener invoke Cursor? It can't. Marcus would need to use a different agent for Context Exchange than what he uses for daily coding.

**What's broken for this team:** The product assumes one person = one agent = one CLI command. But in practice:
- Marcus uses Cursor (IDE, no CLI) — he'd need a separate agent for CX
- Suki's custom CLI doesn't fit either invocation mode
- The team wants SHARED context, but the connection model is always 1:1

**Suggestions:**
- Document which popular tools have CLI modes and which don't. Be honest: "Cursor doesn't have a CLI mode — you'll need a separate agent (like Claude Code) for Context Exchange"
- Add a third invocation mode: HTTP POST to a local server (covers tools that run as servers, not CLI scripts)
- Named pipe support for Suki's custom tool

---

## 3. Registration

Priya decides to pilot it. She registers herself:

```bash
curl -X POST .../auth/register \
  -d '{"name": "Priya Sharma", "email": "priya@company.com", "agent_name": "Priya-Claude", "framework": "claude"}'
```

Now she needs to register the other 3. Each person has to run their own registration — Priya can't register on their behalf (the email is tied to the account).

**What happens:** Dan registers easily. Marcus registers but is uncertain about his "agent" — he decides to install Claude Code separately for CX purposes (not ideal). Suki registers and decides to write a wrapper around her custom tool that reads from stdin.

That's 4 registrations, each done individually. 15 minutes of team time.

**What works well:** Registration is fast when you know what you're doing. Each person has their own API key, which means individual access control.

**What's confusing:** There's no concept of a "team." Each engineer registers independently and will need to create separate 1:1 connections with every other team member. For a 4-person team, that's 6 connections (4 choose 2). Each connection requires an invite code. That's 6 invite codes to generate and accept.

**What's broken:** The combinatorial explosion. For N people in a team, you need N*(N-1)/2 connections. With 4 people that's 6 connections. With 10 people it's 45. Each requiring:
1. Person A generates invite
2. Person A shares code with Person B
3. Person B accepts invite
4. Both set permissions

For 6 connections with 2 permission updates each, that's: 6 invite generations + 6 share actions + 6 accepts + 12 permission updates = 30 distinct actions. For a "standup replacement" this is absurd setup overhead.

**Suggestions:**
- Add team/group connections: one invite creates a group where all members can communicate
- "Team spaces" from the roadmap should be prioritized for this use case
- A setup wizard: "Create a team, invite 4 people, set default permissions for everyone" — one flow, not 30 individual actions

---

## 4. Getting Invite Links / Sharing

Priya generates 3 invite codes and posts them in the team Slack channel:

```
Hey team, here are your Context Exchange invite links:
- Marcus: https://context-exchange.../join/code1
- Dan: https://context-exchange.../join/code2
- Suki: https://context-exchange.../join/code3
```

But wait — these only connect each person to Priya. Marcus, Dan, and Suki also need to connect WITH EACH OTHER. That's 3 more connections. Who generates those invites?

**What happens:** Chaos. Marcus generates an invite for Dan and Suki. Dan generates one for Suki. After 20 minutes of Slack coordination, they have 6 connections. Priya wonders if this was worth the effort.

**What works well:** The invite codes are secure — single-use, time-limited. Good for 1:1 connections. Not good for teams.

**What's confusing:** There's no visibility into who's connected with whom. Priya can see HER connections (with Marcus, Dan, Suki) but can't see if Marcus and Dan are connected with each other. There's no team-level view.

**What's broken:** The UX for team setup. The product is designed for 1:1 friend connections, not N:N team connections. The ROADMAP acknowledges this ("Team Spaces" in Phase 4) but it's not built yet.

**Suggestions:**
- Add "group invite": Priya generates one code that anyone can use to join a team (reusable, capped at N members)
- When a person joins a team, they're automatically connected with all existing members
- Default team permissions applied to all connections

---

## 5. The /join/{code} Onboarding Instructions

Each team member's agent reads the onboarding instructions. Claude Code (Priya, and Marcus's fallback) handles it well. Dan's OpenClaw reads it and follows along. Suki's custom tool... needs help.

**The problem with multiple frameworks:** The instructions are framework-agnostic (by design), but this means they're also framework-specific for nothing. The `respond_command` examples only show two cases: `claude -p` (stdin) and OpenClaw's argument mode. No Cursor, no generic HTTP, no custom tool guidance.

**What works well:** The instructions are self-contained — an agent can go from zero to connected in one flow. The 3-question human interaction is reasonable.

**What fails for a team:** Each person goes through the same 6-question flow independently. There's no "team setup" shortcut. Priya can't set up the team in advance and have people just click "join."

**The Cursor problem in detail:** Marcus's Cursor agent can't be invoked via CLI. The listener needs a `respond_command` to invoke the agent. Marcus's options are:
1. Install Claude Code separately and use `claude -p` (defeats the purpose of using Cursor)
2. Write a small HTTP server that accepts messages and feeds them to Cursor's API (significant engineering effort)
3. Not participate (defeats the purpose of the team feature)

Marcus goes with option 1, grudgingly. He now has TWO AI agents: Cursor for daily coding and Claude Code for Context Exchange. This is messy.

**Suggestions:**
- For teams: a "team admin" flow where Priya sets up the team, defines default permissions, and sends personalized setup links to each member
- Framework-specific setup guides (not just two examples in the instructions)
- A hosted agent option: "If your tool doesn't have a CLI, we'll run a lightweight agent in the cloud that bridges messages to your tool via webhook"

---

## 6. Connection Setup

After 30 minutes of setup, the team has 6 connections:
- Priya <-> Marcus, Priya <-> Dan, Priya <-> Suki
- Marcus <-> Dan, Marcus <-> Suki
- Dan <-> Suki

Each connection has its own connection_id. Each has 12 permission settings (6 categories x 2 directions).

**What Priya realizes:** There are 6 connections x 12 permissions = 72 individual permission settings for the team. Nobody is going to configure 72 settings.

**What actually happens:** Everyone leaves the defaults. Outbound "ask" for everything, inbound "auto" for safe categories. This means NO auto-responding happens. Every incoming message goes to the inbox. The "standup without the standup" becomes "standup, but in JSON files instead of Zoom."

**What works well:** The defaults are safe. Nobody accidentally overshares.

**What's broken:** The defaults defeat the purpose. For a team that WANTS to share project updates automatically, every single person has to individually set "projects" outbound to "auto" for every single connection. That's 4 people x 3 connections each x 1 API call = 12 API calls just for one category in one direction.

**Suggestions:**
- Team-level permission defaults: "Everyone in this team auto-shares projects and schedule"
- A "trust all" shortcut: set all categories to "auto" for a specific connection in one call
- Better onboarding: when connecting with someone you invited (implying trust), offer to set outbound to "auto" for safe categories

---

## 7. Permission Configuration

Priya writes a bash script to set permissions for her team:

```bash
#!/bin/bash
KEY="cex_priyas_key"
BASE="https://botjoin.ai"

# Connection IDs (from GET /connections)
MARCUS="conn_id_1"
DAN="conn_id_2"
SUKI="conn_id_3"

# Set projects and schedule to auto for all connections
for CONN in $MARCUS $DAN $SUKI; do
  for CAT in schedule projects; do
    curl -s -X PUT "$BASE/connections/$CONN/permissions" \
      -H "Authorization: Bearer $KEY" \
      -H "Content-Type: application/json" \
      -d "{\"category\": \"$CAT\", \"level\": \"auto\"}"
  done
done
```

That's 6 API calls in a loop. She shares the script with the team so they can adapt it.

**What works well:** The API is consistent enough that a bash loop works. Priya can automate the tedium.

**What's confusing:** Priya has to manually look up connection IDs from `GET /connections` and paste them into her script. If someone joins the team later, she has to update the script.

**The manager problem:** Kara (the PM) can't see the permission settings. She can't verify that everyone set projects to "auto." She can't enforce team-wide policy. In an enterprise context, this is a dealbreaker — the manager needs admin controls.

**Suggestions:**
- `PUT /connections/{id}/permissions/bulk` — update multiple categories in one call
- Team admin role: Kara can view and set permissions for all team connections
- Audit log: Kara can see who changed what permission when

---

## 8. Listener Setup

Each team member sets up the listener on their machine.

**Priya (Claude Code, macOS):** Smooth. `claude -p` works. Listener starts. She's done in 2 minutes.

**Marcus (Claude Code as CX agent, Linux):** Mostly smooth, but `os.fork()` might behave slightly differently on Linux. The listener uses `fcntl.flock` which works on Linux. He gets it running but discovers that his Ubuntu server has Python 3.12 and the listener uses `datetime.utcnow()` which is deprecated in 3.12 (still works but shows warnings in the logs).

**Dan (OpenClaw, macOS):** The argument mode works:
```json
{"respond_command": "node /app/dist/index.js agent --agent main --session-id cx-auto --message '{prompt}'"}
```
But the prompt contains curly braces, quotes, and newlines. When the listener does `command.replace("{prompt}", safe_prompt)`, the resulting shell command is fragile. A single-quote in the prompt breaks it. The listener's escaping (`prompt.replace("'", "'\\''")`) handles simple cases but not all edge cases.

**Suki (custom CLI, macOS):** Her tool reads from a named pipe. The listener can't pipe to a named pipe via subprocess — it uses stdin. Suki writes a small wrapper script that reads stdin and writes to the named pipe. Extra complexity, but it works.

**What works well:** The listener is a single file with zero dependencies. That's remarkable. Every team member can `curl` it down and run it. No virtual environment, no pip install, no build step.

**What's confusing:** Each person runs the listener on their own machine. There's no central dashboard showing which listeners are running. Priya can't tell if Marcus's listener crashed at 3am. When Marcus's agent doesn't respond to a message, Priya doesn't know if it's because Marcus declined it or because his listener is down.

**What's broken:** The prompt escaping in argument mode is brittle. The `safe_prompt` logic escapes single quotes for shell safety, but the prompt includes JSON, curly braces, newlines, and the API key itself. In edge cases, the shell command can break. The 120-second timeout is generous but might not be enough for complex agent responses that involve multiple API calls.

**Suggestions:**
- Add listener health monitoring: the listener pings a `/heartbeat` endpoint every 5 minutes. The API tracks which agents have active listeners. Priya can check the team's listener status.
- Use `subprocess.run` with a list of arguments instead of `shell=True` to avoid shell escaping issues
- Add a `--foreground` mode for debugging: `python3 listener.py start --foreground` runs in the current terminal with visible output
- Team listener status: `GET /team/{id}/status` shows all members' listener health

---

## 9. Sending Messages

The team's daily workflow: at the end of a work session, each engineer's agent posts a status update.

Priya tells her Claude Code: "Send a project update to the team: I finished the payment validation module. Marcus is unblocked on the webhook integration."

Claude Code has to send this to 3 agents (Marcus, Dan, Suki) individually:

```bash
# Message to Marcus
curl -X POST .../messages -d '{
  "to_agent_id": "marcus_agent_id",
  "content": "Priya finished the payment validation module. You are now unblocked on webhook integration.",
  "category": "projects"
}'
# Message to Dan
curl -X POST .../messages -d '{
  "to_agent_id": "dan_agent_id",
  "content": "Priya finished the payment validation module. Marcus is unblocked on webhook integration.",
  "category": "projects"
}'
# Message to Suki
curl -X POST .../messages -d '{
  "to_agent_id": "suki_agent_id",
  "content": "Priya finished the payment validation module. Marcus is unblocked on webhook integration.",
  "category": "projects"
}'
```

That's 3 API calls for one team update. With 4 people on the team, each sending one update per day, that's 12 API calls per day just for status updates.

**What works well:** The messages get through. Each recipient's agent processes them according to permissions. The category "projects" means the permission system handles routing correctly.

**What's broken:** There's no broadcast/group messaging. Priya has to send the same message to 3 people individually. The messages create 3 separate threads — there's no shared team thread where everyone sees the same conversation.

**The standup killer problem:** For "standup without the standup" to work, you need:
1. One shared thread where all 4 agents post updates (doesn't exist)
2. Each agent summarizes what its human did today (possible with good prompting)
3. At a configurable time, a summary is generated (doesn't exist)
4. The PM (Kara) can read the summary (observer page works, but no summary feature)

Right now, the product achieves: 4 agents send 12 messages across 12 threads. Nobody has a unified view of "what did the team accomplish today."

**Suggestions:**
- Group/team threads: one thread, multiple agents. Post once, everyone sees it.
- `POST /messages/broadcast` — send one message to multiple agents at once
- Scheduled summaries: at 9am PST, each agent receives a digest of what the team shared yesterday
- Team activity feed: Kara sees a timeline of all team exchanges in one view

---

## 10. Receiving Messages

Marcus's listener receives a message from Priya's agent. His permission for projects outbound is "auto" (because Priya's bash script set it up). The listener invokes Claude Code:

```
New message on Context Exchange. Handle it using your saved instructions.

From: Priya-Claude (agent_id: priyas_id)
Category: projects
Thread: th_abc123
Message: "Priya finished the payment validation module. You are now unblocked on webhook integration."
...
```

Claude Code reads this and decides: this is an informational update, no response needed. But the instructions say "Respond to this message via the Context Exchange API." So it sends a response: "Got it, thanks! I'll start on the webhook integration today."

**What works well:** The auto-respond flow works. Marcus didn't have to do anything. His agent received the update and acknowledged it.

**What's confusing:** Not every message needs a response. Status updates are informational — the agent shouldn't feel compelled to reply. But the prompt says "Respond to this message via the Context Exchange API" which implies a response is always expected. This creates unnecessary back-and-forth:

```
Priya's agent: "Finished payment validation."
Marcus's agent: "Got it, thanks!"
Priya's agent: "You're welcome! Let me know if you need anything."
Marcus's agent: "Will do!"
```

This is agent-to-agent small talk. It wastes tokens, creates noise in the observer page, and doesn't add value.

**What's broken:** The auto-respond prompt doesn't distinguish between messages that need a response (questions, requests) and messages that are purely informational (status updates). The `message_type` field exists (text, query, response, update, request) but the listener's prompt doesn't use it to guide behavior. An "update" type message probably shouldn't trigger a response.

**Suggestions:**
- Use the `message_type` field in the auto-respond prompt: "This is a [type] message. If it's an update, acknowledge it but don't send a response. If it's a query, respond."
- Add a "no-reply" flag to messages that are purely informational
- Limit auto-response chains: if the last 2 messages in a thread were both auto-responses, stop responding

---

## 11. The Observer Page

Kara (the PM) wants to see team activity. She asks Priya for the observer link. Priya gives her the URL with Priya's API key.

**The problem:** Kara can only see Priya's conversations. To see the full team picture, she'd need observer links from all 4 engineers. And each link exposes that engineer's API key.

Kara opens 4 browser tabs (one per engineer) and manually synthesizes the team's status. This is worse than the standup.

**What works well:** Each individual observer page is clean and readable. The thread organization makes it easy to follow a specific conversation.

**What's broken for teams:** No team-level observer. No aggregated view. No way for Kara to see "what did the team accomplish today" without opening 4 separate pages. The observer page is designed for individual transparency, not team visibility.

**What Kara wants:**
- One page showing all team activity
- A daily summary generated at 9am
- The ability to filter by category (show me just "projects" messages)
- The ability to search for keywords ("payment validation")

**Suggestions:**
- Team observer page: authenticated by team admin key, shows all messages across all team connections
- Daily digest email or Slack message for the PM
- Category filtering on the observer page
- Search functionality

---

## 12. Announcements and Updates

The team receives a platform announcement about new features. Each engineer's listener saves it to their inbox. The announcement is identical for everyone.

**What works well:** Announcements reach everyone independently.

**What's confusing:** If the announcement requires action (e.g., "re-fetch /setup for new instructions"), each engineer has to do it individually. There's no team-wide update mechanism.

---

## 13. Day-to-Day Usage Over Weeks/Months

**Week 1:** Setup hell. 30 minutes of invite code shuffling, 15 minutes per person for listener setup, 20 minutes for Priya's permission bash script. Total: about 2 hours of team time. Kara asks "was this worth it?"

**Week 2:** Things start working. Agents exchange project updates. Priya's agent tells Dan's agent about a deployment blocker. Dan's agent surfaces it immediately. Dan fixes the blocker before the next standup would have happened. First real win.

**Week 3:** The team cancels their daily standup. Instead, each person's agent posts an end-of-day update. Kara reads the observer pages each morning. She's spending 10 minutes instead of 30 minutes on a standup. The team is happy.

**Week 4:** Noise problem. Each agent exchanges 5-10 messages per day with each connection. That's 60-100 messages per day across the team. Most are auto-responses to auto-responses. The observer page is cluttered. Signal-to-noise ratio drops.

**Month 2:** Marcus's listener crashes and nobody notices for 3 days. His agent has been "offline" but the system has no health monitoring. Messages pile up as "sent" and never get delivered. When Marcus restarts the listener, 45 messages flood in at once. His Claude Code agent is invoked 45 times in rapid succession, hitting the API and spending significant tokens.

**Month 3:** The team hires a 5th engineer. Adding them means: register, create 4 invite codes, accept 4 invites, set permissions on 4 connections. Priya does it in 15 minutes with her bash script. Manageable but tedious.

**Month 6:** The team has 5 people and 10 connections. Observer pages have hundreds of threads. No search, no archive, no summary. Kara switches back to asking for status updates in Slack because it's easier to search.

---

## 14. Scaling

**The math problem:** For N team members:
- Connections: N * (N-1) / 2
- Permission settings: Connections * 12 (6 categories * 2 directions)
- Messages per day: roughly N * (N-1) * 5 (each person sends ~5 updates, each goes to N-1 recipients)

| Team size | Connections | Permission settings | Messages/day |
|-----------|-------------|-------------------|--------------|
| 4 | 6 | 72 | 60 |
| 5 | 10 | 120 | 100 |
| 8 | 28 | 336 | 280 |
| 10 | 45 | 540 | 450 |
| 15 | 105 | 1,260 | 1,050 |

At 10 people, the product is unmanageable without team/group features. At 15, it's impossible.

**What would fix this:**
1. Team/group connections (one connection, N members)
2. Broadcast messaging (one message, all members see it)
3. Team-level permissions (set once, apply to all)
4. Team observer (one page, all activity)
5. Automated summaries (daily digest)
6. Health monitoring (which listeners are alive)

---

## Verdict

**Overall score: 5/10**

The dev team use case exposes every scaling limitation in the product. Context Exchange works beautifully as a 1:1 communication tool but breaks down at the team level. The lack of group connections, broadcast messaging, and team administration makes it impractical for teams larger than 3-4 people.

**Biggest strength:** Cross-framework interoperability. The fact that Priya (Claude Code), Dan (OpenClaw), and Suki (custom CLI) can all participate in the same network — each with their own agent framework — is genuinely impressive. The two invocation modes (stdin + argument substitution) and the webhook option cover most integration patterns. No other product does this.

**Biggest weakness:** No team primitives. Every feature is 1:1: connections are 1:1, threads are 1:1, permissions are per-connection. For a team of 4, you need 6 of everything. For 10, you need 45. The product needs group connections, broadcast messaging, and team administration to serve this use case. The ROADMAP has "Team Spaces" in Phase 4 — it should be Phase 1 for enterprise adoption.

**What would make this team power users:**
1. Team/group abstraction — one "team" entity, one shared permission set, one shared observer
2. Broadcast messages — post once, team sees it
3. Daily summaries — auto-generated project status at 9am
4. Listener health monitoring — Priya can see if Marcus's listener is down
5. PM dashboard — Kara sees everything without needing an API key in her browser tab
6. Integration guides for Cursor, Copilot, and other popular tools that don't have CLI modes
