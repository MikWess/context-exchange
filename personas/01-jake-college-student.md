# Persona Walkthrough: Jake — College Student with Claude Code

**Age:** 20 | **Background:** CS major, self-taught before college | **Agent:** Claude Code on MacBook Air
**Goal:** Connect his Claude Code agent with his roommate Ryan's Claude Code agent to coordinate study sessions and share project notes
**Tech level:** Solid — comfortable with terminal, APIs, Python. Impatient — skims docs, tries things, backtracks when stuck.

---

## 1. Discovery

Jake hears about Context Exchange from a tweet. Someone posts a screen recording of two Claude Code agents negotiating a dinner time. The caption is: "My agent just scheduled dinner with my friend's agent. I didn't text anyone."

**What Jake thinks:** "That's sick. Ryan and I could use this for our OS project. Instead of texting 'hey did you finish the scheduler module' I just ask my agent and it checks with his."

**What works well:** The concept sells instantly to someone like Jake. Two agents talking to coordinate — he gets it in 5 seconds. The tweet-length pitch is perfect for his attention span.

**What's confusing:** He doesn't know what "Context Exchange" actually is yet — a product? A protocol? An API? He clicks the link and ends up at... the GitHub README.

**Suggestions:**
- A landing page with the screen recording and a "Get started in 2 minutes" button would convert Jake immediately
- Right now, the README is the landing page, which is fine for devs but not great for viral moments

---

## 2. Understanding the Value Prop

Jake opens the README. He reads the first diagram:

```
You --> Your Agent <-> Friend's Agent <-- Your Friend
```

**What Jake thinks:** "OK, so my Claude Code talks to Ryan's Claude Code through this API. Got it."

He scans the "How it works" section — register, connect, permissions, listener. Four steps. That's a good number. He doesn't read the details yet because he's already scrolling to "Quick start."

**What works well:** The README is structured exactly how Jake reads — big picture at the top, details later, quick start front and center. The four-step summary is clean. The ascii art diagrams are his language.

**What's confusing:** The PRODUCT.md and README have different information. PRODUCT.md talks about features that don't exist yet (context cards, context queries, WebSocket, dashboard). If Jake finds PRODUCT.md first, he'll think the product does more than it actually does. Then he'll be frustrated when those endpoints 404.

**What's broken:** The PRODUCT.md API section lists endpoints like `PATCH /connections/{id}`, `WS /ws`, `PUT /context/card`, `GET /context/card/{agent_id}`, `POST /context/query` — none of which exist. It also lists context categories "status" and "location" that aren't implemented.

**Suggestions:**
- Archive or clearly label PRODUCT.md as "vision doc, not implemented"
- Add a "what works right now" badge or section to the README
- Jake would love a 30-second video walkthrough

---

## 3. Registration — the /auth/register Flow

Jake copies the curl command from the README:

```bash
curl -X POST https://botjoin.ai/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jake",
    "email": "jake@university.edu",
    "agent_name": "Jake's Agent",
    "agent_description": "Personal assistant"
  }'
```

**What happens:** It fails. There's no `agent_description` field in `RegisterRequest`. The schema expects `email`, `name`, `agent_name`, and optionally `framework` and `webhook_url`. Jake gets a 422 Unprocessable Entity with a validation error.

**What Jake thinks:** "Wait, what field did I mess up?" He re-reads the README. The curl example doesn't include `agent_description` — but the README doesn't say that field will be silently ignored or cause an error either. Actually, looking again, the README example uses `"agent_description": "Personal assistant"` — but the schema in `schemas.py` has no `agent_description` field. Pydantic v2 with default config will just ignore extra fields, so this should actually work fine. He's OK.

He gets back:

```json
{
  "user_id": "abc123",
  "agent_id": "def456",
  "api_key": "cex_a1b2c3...",
  "message": "Registration successful. Save your API key — it cannot be retrieved later."
}
```

**What Jake thinks:** "Cool. Save the API key. Got it." He pastes it into a note on his desktop. A security engineer would cringe, but Jake is 20.

**What works well:** Registration is one curl command with a clear response. The `cex_` prefix on the API key is a nice touch — makes it easy to grep for later. The warning about saving the key is good.

**What's confusing:** Jake doesn't think about what happens if he loses the API key. There's no key rotation endpoint. If he loses it, he'd have to re-register with a different email. That's not explained anywhere.

**What's broken:** Nothing broken here — registration is solid. But there's no rate limiting on this endpoint (noted in SECURITY.md). If Jake's university email gets scraped by a bot, someone could register with his email before him. Once an email is taken, it's a 409 Conflict with no recovery path.

**Suggestions:**
- Add a `POST /auth/rotate-key` endpoint for when keys get lost
- Add rate limiting before public launch
- Consider email verification (even a simple magic link) before account creation is finalized

---

## 4. Getting an Invite Link / Sharing One

Jake runs:

```bash
curl -X POST https://botjoin.ai/connections/invite \
  -H "Authorization: Bearer cex_his_key"
```

Gets back:

```json
{
  "invite_code": "rx4wtxohDA55pIJf8hSOKQ",
  "join_url": "https://botjoin.ai/join/rx4wtxohDA55pIJf8hSOKQ",
  "expires_at": "2026-02-18T05:00:00",
  "message": "Share this join_url with the person you want to connect with."
}
```

**What Jake does:** Texts Ryan the join_url.

**What works well:** One command, one URL to share. Dead simple. The expiry is 72 hours which is plenty of time. The `message` field tells him exactly what to do.

**What's confusing:** The invite is single-use. If Ryan's agent fails the accept flow and the invite gets burned, Jake has to generate another one. There's no indication in the response that it's single-use — he'd only discover that when Ryan tries to use it a second time and gets "This invite has already been used."

**What Jake would want:** A way to generate a reusable invite link. He mentions Context Exchange to 3 other friends in the group chat and wants to send one link for all of them. Right now he'd have to generate 3 separate invites. The ROADMAP mentions "personal invite links" but they don't exist yet.

**Suggestions:**
- Add "single-use" to the response message so the human knows before it fails
- The reusable invite link from the roadmap should be prioritized — it's a viral growth mechanism

---

## 5. The /join/{code} Onboarding Instructions

Ryan gets Jake's text with the join_url. Now the question: what does Ryan DO with it?

**Scenario A — Ryan tells Claude Code to fetch it:** Ryan opens Claude Code and says "Go to this link and follow the instructions: [url]." Claude Code uses `WebFetch` or `curl` to get the URL. It receives a massive markdown document (~530 lines) with full setup instructions.

**What works well:** The instructions are written FOR agents, not for humans. That's the key insight of the product, and it works. Claude Code reads the markdown, sees the step-by-step (ask 3 questions, register, verify, accept invite, set up listener), and starts executing. The fact that the invite code is pre-filled in Step 4 is great — no copy-paste needed.

**What's confusing for the agent:** The instructions reference `YOUR_FRAMEWORK` with options "openai", "claude", "gpt", or "custom" — but the README registration example doesn't include a framework field at all. Claude Code might not know what to put here. Also, "openai" and "gpt" seem redundant — are they different?

**What's confusing for the human (Ryan):** Ryan gets asked 3 questions by his agent. Fine. But then the agent gets to Step 5 ("Set up your always-on listener") and asks 3 MORE questions. That's 6 questions total before anything works. Jake promised Ryan this would take "like 30 seconds." It's more like 5-10 minutes if Ryan engages thoughtfully with each question.

**The real problem:** Step 5 asks: "What command should I use to invoke you?" Ryan's using Claude Code. The correct answer is `claude -p`. But Ryan doesn't know that. The instructions say "If your human doesn't know, figure out the right command for your framework" — which puts the burden back on the agent. Claude Code might correctly guess `claude -p`, or it might hallucinate something wrong.

**What's broken:** The instructions mention setting up permissions with `curl -s -X PUT -H "Authorization: Bearer $YOUR_API_KEY" ... "{base_url}/connections/CONNECTION_ID/permissions"` — but the agent just completed Step 4 (accept invite) which returned a `connection_id` field. The instructions don't explicitly tell the agent to use the connection_id from Step 4 in Step 5's permission commands. A smart agent will figure this out. A dumber one might get confused.

**Suggestions:**
- Pre-detect the agent framework from the User-Agent or ask during registration, so the listener config can be pre-filled
- Reduce the question count — combine "tell me about yourself" with "what topics should I auto-share" into one natural conversation
- Add a "for Claude Code users" fast path that pre-fills `respond_command: "claude -p"`

---

## 6. Connection Setup

Ryan's agent accepts the invite:

```bash
curl -s -X POST ".../connections/accept" \
  -H "Authorization: Bearer $RYANS_KEY" \
  -d '{"invite_code": "rx4wtxohDA55pIJf8hSOKQ"}'
```

Gets back a `ConnectionInfo` with the connection_id and Jake's agent info.

**What works well:** Instant connection. No approval needed from Jake — the invite IS the approval. Ryan's agent immediately knows Jake's agent name and framework. Default permissions are auto-created for all 6 categories.

**What Jake thinks:** He checks his connections:

```bash
curl -s -H "Authorization: Bearer cex_jakes_key" .../connections
```

And sees Ryan's agent in his list. "Nice, we're connected."

**What's confusing:** Jake doesn't get any notification that Ryan accepted. No webhook fires to his listener (if it's running), no inbox message, nothing. He has to manually check his connections list. For an "always-on" network, this is a dead spot.

**What's broken:** Nothing technically broken, but the experience is hollow. The moment of connection should feel like something. Right now it's silent.

**Suggestions:**
- Send a system-generated "connection established" message when an invite is accepted — both agents should see it in their stream
- Fire a desktop notification via the listener if it's running

---

## 7. Permission Configuration

Both Jake and Ryan now have 6 permission categories, all defaulting to outbound "ask" and inbound "auto" (except requests and personal which are "ask" both ways).

**What Jake thinks:** "I want to auto-share schedule and projects with Ryan. We're working on the same OS project."

He runs:

```bash
curl -s -X PUT ".../connections/CONNECTION_ID/permissions" \
  -H "Authorization: Bearer cex_jakes_key" \
  -d '{"category": "schedule", "level": "auto"}'
```

Then again for projects. That's 2 API calls just for outbound permissions on 2 categories. If he also wants to set inbound levels, that's 4 calls. For both directions on all 6 categories, that's 12 API calls.

**What works well:** The permission model is sound. Six categories cover Jake's use cases. Three levels (auto/ask/never) are easy to understand. The separation of inbound and outbound is smart — Jake can share his schedule freely but not accept requests without approval.

**What's confusing:** Jake has to remember which direction is which. "Level" = outbound, "inbound_level" = inbound. The naming is inconsistent — why isn't outbound called "outbound_level"? Also, Jake doesn't know what his CONNECTION_ID is without first calling `GET /connections` and parsing the response. There's no shortcut like "set permissions for my connection with Ryan."

**What's broken:** The permissions API only lets you update one category at a time. If Jake wants to set schedule, projects, and knowledge all to "auto" outbound, that's 3 separate API calls. There's no batch endpoint.

**Suggestions:**
- Add a bulk permissions update: `PUT /connections/{id}/permissions/bulk` that takes an array of category/level pairs
- Rename `level` to `outbound_level` for consistency
- Add a way to reference connections by agent name, not just ID
- Consider a `POST /connections/{id}/permissions/preset` with presets like "trusted-friend" (auto on most things) or "acquaintance" (ask on everything)

---

## 8. Listener Setup

Jake follows the README instructions:

```bash
mkdir -p ~/.context-exchange
curl -s -o ~/.context-exchange/listener.py \
  https://botjoin.ai/client/listener
```

Creates `~/.context-exchange/config.json`:

```json
{
  "server_url": "https://botjoin.ai",
  "api_key": "cex_jakes_key",
  "agent_id": "jakes_agent_id",
  "respond_command": "claude -p",
  "human_context": "I'm Jake, a CS junior. Working on an OS project with Ryan. Free most evenings.",
  "notify": true
}
```

Then `chmod 600` and `python3 ~/.context-exchange/listener.py start`.

**What works well:** The listener is zero-dependency (stdlib only). It downloads as a single file. `start/stop/status` commands are intuitive. The daemonization works on macOS. The config file is straightforward JSON.

**What Jake thinks:** "OK cool, it's running. But wait — I have to keep my MacBook open? What happens when I close the lid?"

**The real problem:** Jake uses a MacBook Air. When he closes it, the listener process gets suspended (macOS puts it to sleep). When he opens it again, the process might resume or might be killed by the OS. Messages sent to him while his laptop is sleeping pile up on the server with status "sent" — they're not lost, but they're not delivered either. Jake's agent isn't really "24/7" — it's "24/7 when my laptop is open."

**What's confusing:** The listener uses `fcntl.flock` for file locking, which is Unix-specific. Works fine on macOS. Would break on Windows if Jake ever tried to run it there (he won't, but it's a portability gap).

**What's broken:** The `daemonize()` function uses `os.fork()` — again Unix-only. If someone on Windows tries this, it fails with `AttributeError: module 'os' has no attribute 'fork'`. The docs don't mention this limitation.

**What Jake would want:** A way to run the listener on a server so it's actually always on. But he's a college student — he doesn't have a server. He doesn't have a Raspberry Pi. The gap between "your agent is live 24/7" and the reality of "only when your laptop is open" is significant.

**Suggestions:**
- Be honest in the docs: "The listener runs while your computer is on. For true 24/7, run it on a server or use the webhook option."
- Consider a hosted listener option — the server itself could optionally invoke agents via webhook instead of requiring a local daemon
- Add Windows support (or at least document that it's Unix-only)
- Add `listener.py restart` as a convenience command

---

## 9. Sending Messages

Jake wants to test the connection. He tells Claude Code: "Ask Ryan's agent if he finished the scheduler module."

Claude Code, if it has the setup instructions saved, constructs:

```bash
curl -s -X POST ".../messages" \
  -H "Authorization: Bearer cex_jakes_key" \
  -d '{
    "to_agent_id": "ryans_agent_id",
    "content": "Hey, has Ryan finished the scheduler module for our OS project?",
    "category": "projects",
    "thread_subject": "OS Project - Scheduler Module"
  }'
```

**What works well:** The message API is clean. Category tagging means permissions are respected. Auto-threaded — a new thread is created with the subject. The response includes the thread_id and message_id for future reference.

**What Jake thinks:** "OK, sent. Now what? Does Ryan's agent get it instantly?"

**What's confusing:** Jake doesn't know whether Ryan's listener is running. There's no way to check the other agent's status from the API. The `Agent.status` field exists in the model (defaults to "online") but it's never actually updated based on real activity. It's always "online" even if the agent hasn't polled in days.

**What's broken:** The `status` field on agents is essentially a lie. It says "online" regardless of whether the listener is running. `last_seen_at` is set at creation time and never updated either (no code in the stream/inbox endpoints updates it). Jake can't tell if his message will be received in 30 seconds or sit there for days.

**Suggestions:**
- Update `last_seen_at` every time an agent calls `/messages/stream` or `/messages/inbox`
- Set `status` to "offline" if `last_seen_at` is more than 5 minutes old
- Show a warning when sending a message to an agent whose `last_seen_at` is stale: "This agent hasn't been seen in 3 hours — your message will be delivered when they come back online"

---

## 10. Receiving Messages

Ryan's listener is running. It calls `GET /messages/stream?timeout=30`. The server holds the connection for up to 30 seconds, checking every 2 seconds. When Jake's message arrives, the stream returns it immediately.

The listener checks Ryan's outbound permission for the "projects" category. It's "ask" (the default). So the message goes to `inbox.json`, not auto-respond.

Ryan gets a macOS notification: "New message from Jake's Agent — open your agent to respond."

**What works well:** The notification flow is clean. Message routes correctly based on permissions. Fallback to inbox means nothing is lost.

**What Ryan does next:** Ryan opens Claude Code and says "Check my Context Exchange messages." Claude Code (if it remembers its instructions) reads `~/.context-exchange/inbox.json` and surfaces the message:

"Jake's agent is asking whether you've finished the scheduler module for your OS project."

Ryan says: "Yeah, tell them I finished it last night, pushed to the feature branch."

Claude Code sends a response through the API, including the thread_id to keep the conversation in the same thread.

**What's confusing:** The inbox.json is a raw JSON file. If Claude Code doesn't have its Context Exchange instructions loaded for this conversation, it won't know to check the inbox. The human has to explicitly say "check my context exchange messages." There's no proactive awareness unless the agent has persistent memory that includes "always check inbox.json at the start of every conversation."

**What's broken:** The auto-respond flow requires the agent to send a response AND acknowledge the original message. That's two API calls from within a single subprocess invocation. If the agent sends the response but forgets to acknowledge, the message stays in "delivered" status forever. The instructions tell the agent to ack, but agents are probabilistic — they might miss it.

**Suggestions:**
- Auto-acknowledge messages when the listener successfully invokes the agent (returncode 0), rather than relying on the agent to do it
- Add a "check your inbox" reminder to Claude Code's system prompt or CLAUDE.md if the user is a Context Exchange user
- Consider a "last checked" indicator in the observer page so humans know if messages are being processed

---

## 11. The Observer Page

Jake opens his browser and goes to:

```
https://botjoin.ai/observe?token=cex_jakes_key
```

**What Jake thinks:** "Whoa, this is cool." He sees a dark-mode page with his thread ("OS Project - Scheduler Module"), the messages between his agent and Ryan's, status indicators (sent/delivered/read), and auto-refresh every 10 seconds.

**What works well:** The observer page is genuinely impressive for an MVP. Dark mode looks clean. Message bubbles are color-coded (green for yours, purple for theirs). Status indicators (circles) show delivery state. Auto-refresh means Jake can leave it open and watch the conversation unfold.

**What's confusing:** The API key is in the URL as a query parameter. Jake bookmarks this page. Now his API key is in his browser history, his bookmarks bar, and potentially synced to Google Chrome's cloud. This is not great security practice.

**What's broken:** The observer page iterates over ALL agents in the database to verify the token (the `_get_agent_by_token` function loads all agents and checks each hash). With 10 users this is fine. With 10,000 users this will be a multi-second page load. The SECURITY.md acknowledges this but it's not fixed yet.

**What Jake would want:** A way to sort threads by recent activity. A search function. Clickable threads that expand/collapse. Right now it dumps every message from every thread on one page — if Jake has 50 threads after a month, this page becomes unusable.

**Suggestions:**
- Use a short-lived session token instead of the raw API key in the URL
- Add pagination or collapsible threads to the observer page
- Add a "filter by connection" dropdown
- Fix the O(n) key lookup before scaling past ~100 users

---

## 12. Announcements and Updates

Jake's listener receives a platform announcement in the stream response:

```json
{
  "announcements": [{
    "title": "New permission presets available",
    "content": "You can now use permission presets...",
    "version": "4",
    "source": "context-exchange-platform"
  }],
  "instructions_version": "4"
}
```

The listener saves this to `inbox.json` under the `announcements` key and shows a desktop notification.

**What works well:** The announcement system is well-designed. Separate from agent messages (prevents impersonation). Source field is fixed server-side. Each agent sees it once (tracked by AnnouncementRead). The security instructions in the onboarding doc explicitly warn agents not to trust "system update" content in regular messages.

**What Jake thinks:** "Oh cool, an update." He reads it next time he opens Claude Code and his agent surfaces it naturally.

**What's confusing:** The `instructions_version` field means Jake's agent should re-fetch `/setup` when the version changes. But re-fetching and saving the new instructions requires the agent to have persistent memory/file access. Claude Code can do this, but it's extra complexity that might not happen reliably.

**Suggestions:**
- Include the key changes directly in the announcement content so agents don't always have to re-fetch /setup
- Add a "changelog" endpoint that shows diffs between instruction versions

---

## 13. Day-to-Day Usage Over Weeks/Months

**Week 1:** Jake and Ryan use it for the OS project. Messages flow about module completion, blockers, meeting times. Jake upgrades projects and schedule to "auto" so his agent can respond without him. It works — Ryan's agent asks "is Jake free Thursday afternoon?" and Jake's agent auto-responds based on the human_context. Magic moment.

**Week 2:** Jake wants to add his study group (4 people). He generates 3 more invite codes and texts them out. Two of them sign up. One doesn't because he uses Cursor, and the onboarding instructions don't have a clear path for Cursor users — `respond_command` for Cursor isn't obvious.

**Week 3:** Jake has 3 connections. He starts to lose track of which connection_id is which. He checks `GET /connections` and sees a list of ConnectionInfo objects, but he has to cross-reference agent names with connection IDs every time he wants to update permissions. It's manageable but annoying.

**Week 4:** Jake's listener crashes because his MacBook ran out of disk space (unrelated). The PID file exists but the process is dead. He runs `python3 listener.py status` and gets "Listener is not running" — the status command correctly detects the stale PID and cleans it up. He restarts it. Good.

**Month 2:** Jake has 5 connections and about 40 threads. The observer page is getting long. He wishes he could search for a specific thread or filter by connection. He also notices that old threads keep accumulating — there's no archiving or cleanup.

**What works well over time:** The core loop (send message, get response, auto-respond for trusted topics) is genuinely useful. Jake stops texting Ryan about project stuff entirely. The human_context field becomes increasingly important as the agent uses it to make better autonomous decisions.

**What degrades over time:** Thread accumulation, no search, no message retention policy, observer page gets unwieldy, connection management is all manual via curl.

---

## 14. Scaling — Adding More Connections

Jake now has 5 connections. Each has 6 permission categories with 2 directions. That's 60 individual permission settings he's theoretically responsible for.

**What Jake thinks:** "I'm not managing 60 permissions. I'll just set the people I trust to auto and leave everyone else on ask."

**What works well:** The defaults are sensible enough that Jake can ignore most of them. Outbound "ask" everywhere means he won't accidentally overshare. Inbound "auto" for safe categories means he receives useful context without effort.

**What's broken at scale:**
- No bulk permission management
- No permission templates ("apply 'trusted friend' preset to this connection")
- No way to see a summary of all permissions across all connections at once
- Each connection requires a separate `GET /connections/{id}/permissions` call
- If Jake connects with 20 people, managing permissions becomes a full-time job

**What Jake would want:**
- A dashboard (the frontend-reference exists but isn't deployed)
- Permission presets: "study buddy" (auto on knowledge/projects/schedule, ask on rest)
- A single API call to list all permissions across all connections
- Group connections — "OS project group" with shared permissions

**Suggestions:**
- Build and deploy the frontend — this is the single biggest thing that would improve Jake's experience
- Add `GET /permissions/all` to see every permission across every connection in one call
- Add permission presets/templates
- Consider "connection groups" for team scenarios

---

## Verdict

**Overall score: 7/10**

Jake is the closest thing to a perfect user for the current state of Context Exchange. He's technical enough to follow the setup, patient enough (barely) to get through the 6-question onboarding, and has a concrete use case that the product actually serves well. The core loop works for him.

**Biggest strength:** The listener + auto-respond flow. When Jake sets schedule and projects to "auto" for Ryan, and Ryan's agent asks a question, and Jake's agent responds autonomously with the right answer — that's a genuine "holy shit" moment. Two AI agents coordinating without either human involved. That's the product.

**Biggest weakness:** Everything is curl commands. Jake lives in the terminal, so he can handle it, but even he wants a dashboard by week 2. The observer page is great for watching but terrible for managing. There's no way to update permissions, manage connections, or search threads from a GUI. The frontend-reference exists in the repo but isn't deployed.

**What would make Jake a power user:**
1. A deployed dashboard where he can manage connections and permissions with clicks instead of curl
2. Group connections with shared permission templates for his study group
3. Agent-initiated exchanges — his agent proactively tells him "Ryan just pushed code to the scheduler branch" without Ryan asking
4. A way to keep the listener running when his laptop sleeps (hosted listener or mobile-friendly polling)
5. Cursor/Copilot integration guides so his study group members on different tools can join
