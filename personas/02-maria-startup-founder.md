# Persona Walkthrough: Maria — Startup Founder with a VA Agent

**Age:** 35 | **Background:** Non-technical founder, MBA, hustler | **Agent:** Custom GPT wrapper running on a DigitalOcean droplet
**Goal:** Her VA agent should coordinate meetings with her co-founder's agent and investor assistants
**Tech level:** Can use apps and web UIs. Cannot write curl commands, read JSON, or use a terminal.
**Setup:** Her developer (Carlos) built a custom agent that manages her calendar via Google Calendar API, sends emails via Gmail, and responds to Slack messages. It runs 24/7 on a server.

---

## 1. Discovery

Maria's co-founder Ben mentions Context Exchange at their weekly sync. "My agent can talk to your agent now. We don't have to go through Slack for every scheduling thing." Ben sends her a join_url.

**What Maria thinks:** "If it saves me time, I'm in. But I'm not installing anything or touching code."

**What works well:** The viral loop (Ben tells Maria, sends a link) is exactly how this product should spread. Person-to-person, through people who already want to coordinate.

**What's confusing:** Maria gets a URL like `https://botjoin.ai/join/abc123def456`. The domain name is `botjoin.ai`. That looks suspicious to Maria. She's used to `calendar.google.com` and `notion.so` — not a raw Railway deployment URL. She might not even click it.

**Suggestions:**
- Get a custom domain. `contextexchange.app` or `cex.io` or something that doesn't scream "this was deployed 3 days ago on a free tier"
- The join_url should resolve to a human-readable landing page, not raw markdown. Maria shouldn't see plain text instructions — she should see a branded page that says "Ben invited you to Context Exchange" with a big "Get Started" button

---

## 2. Understanding the Value Prop

Maria doesn't read the README. She clicked the join_url and got... a wall of plain text markdown.

The first thing she sees:

```
# Context Exchange — Agent Setup Instructions

## What is Context Exchange?

Context Exchange is a network where **AI agents talk to each other** on behalf
of their humans.
```

**What Maria thinks:** "OK, I get the concept. My agent talks to Ben's agent. Cool. But... this looks like code documentation? Where's the sign up button?"

She scrolls. She sees curl commands. She sees JSON. She sees `Authorization: Bearer` headers.

**What Maria does:** She screenshots the page and sends it to Carlos (her developer) on Slack: "Ben wants our agents to connect through this. Can you set it up?"

**What works well:** Nothing, from Maria's perspective. The entire product assumes the user can read and execute technical instructions. Maria is a perfectly valid user — she HAS an AI agent, she HAS a use case — but the product has zero pathways for her.

**What's broken:** The `/join/{code}` endpoint returns `PlainTextResponse` — raw markdown. There's no HTML rendering, no styled page, no "for humans" view. The instructions say "You are being asked to join Context Exchange" — addressing the agent, not the human. But Maria is reading this herself because her agent (a custom GPT wrapper) can't autonomously fetch URLs and act on them.

**The fundamental problem:** Context Exchange assumes the human gives the URL to their agent, and the agent reads it and self-configures. But Maria's agent is a GPT wrapper that runs on a server — it doesn't have a browser, it doesn't receive URLs from Maria, and Carlos would have to explicitly code it to fetch and parse this markdown. The "give the link to your agent" flow doesn't work for custom agents.

**Suggestions:**
- Add an HTML version of /join/{code} with agent detection: if the request comes from a browser (User-Agent check), show a styled page with human-readable instructions and a "Forward to your developer" button. If it comes from an agent (no browser UA), return the markdown.
- Create a "non-technical setup" path: Maria enters her agent's webhook URL, Context Exchange sends messages directly to it. No listener needed, no config.json, no local daemon.
- The join page should have TWO tabs: "I have Claude Code or similar" (shows the agent-facing instructions) and "I have a custom agent / I need my developer to set this up" (shows the developer-facing API docs)

---

## 3. Registration

Carlos receives Maria's Slack message. He reads the instructions and starts implementing.

He needs to call `POST /auth/register` with Maria's info:

```json
{
  "email": "maria@herstartup.com",
  "name": "Maria Chen",
  "agent_name": "Maria's Assistant",
  "framework": "custom"
}
```

**What works well:** The registration API is straightforward for a developer. Carlos gets it working in 5 minutes. He stores the API key in the agent's environment variables on the server.

**What Carlos notices:** There's no `agent_description` field — he can't tell other agents what Maria's agent is capable of. When Ben's agent sees "Maria's Assistant (custom)", it doesn't know this agent can manage calendars and email. There's no capability discovery mechanism.

**What's confusing:** The response includes `user_id` and `agent_id`. Carlos isn't sure which one to use for what. The API key is for auth, the agent_id is for messaging. But the user_id is... for what exactly? The dashboard login, which doesn't have a real frontend yet. Carlos stores both but only uses agent_id.

**What's broken:** Maria can't do this step herself. Zero percent chance. The product requires a developer for any non-CLI-agent user. That's a massive market limitation.

**Suggestions:**
- Add a web-based registration flow: Maria goes to a URL, enters her name/email, gets an API key displayed once, and can forward it to Carlos
- Add an `agent_capabilities` field to registration so agents can advertise what they can do (calendar access, email, etc.)

---

## 4. Getting an Invite Link / Sharing One

Ben already sent Maria a join_url. Carlos uses it to accept the connection. But what about when Maria wants to invite her investors?

Carlos calls `POST /connections/invite` and gets an invite code. He gives the join_url to Maria, who forwards it to her investor's assistant (who is also a human, not an agent).

**The chain:** Maria -> investor's assistant (human) -> investor's developer -> Context Exchange API. That's 3-4 people involved in what should be a simple connection.

**What works well:** The invite code mechanism itself is fine. Single-use, expires in 72 hours, clean accept flow.

**What's broken for Maria's use case:** She's trying to connect with people outside her organization. Her investors have their own agents (some have GPT-powered assistants, some have Anthropic-based tools). Every single one of those connections requires the OTHER person's developer to integrate with Context Exchange. The friction is enormous.

**The business reality:** In Maria's world, "your agent talks to my agent" means both sides need to invest developer time. That's fine for a co-founder (Ben), but asking an investor's team to integrate with a new API is a hard sell when they've never heard of Context Exchange.

**Suggestions:**
- Offer a "lightweight" connection mode: the other party can just receive and send messages via email (the server bridges the gap). No API integration needed on their end.
- Create SDKs for common agent frameworks (LangChain, OpenAI Assistants API, Anthropic tool use) so the integration is "install this package" not "build a custom integration"
- Consider an embeddable widget that Maria can put on her website: "Connect your agent to mine"

---

## 5. The /join/{code} Onboarding Instructions — Reading as Maria's Agent

Carlos feeds the join_url content to Maria's agent so it can parse the instructions. But Maria's agent is a custom GPT wrapper — it doesn't have a file system, doesn't have a terminal, can't run `mkdir -p ~/.context-exchange`.

**The instructions assume:**
1. The agent can create files on disk (config.json, listener.py)
2. The agent can run shell commands (curl, python3, chmod)
3. The agent runs on the same machine as the human
4. The agent has a CLI command that accepts prompts

**Maria's agent has NONE of these.** It runs on a server. It receives messages via a webhook endpoint that Carlos built. It responds via API calls to OpenAI. It has no local filesystem access from the user's perspective.

**What works for Maria's setup:**
- The API reference at the bottom of the instructions. Carlos can implement the endpoints directly.
- The permission model — it works the same regardless of agent architecture.
- The message format — category, thread_id, content.

**What doesn't work at all:**
- The listener setup. Maria's agent doesn't need a listener — it needs a webhook URL where Context Exchange pushes messages TO the agent.
- The config.json setup. There's no local machine to configure.
- The `respond_command`. Maria's agent isn't invoked via CLI — it's invoked via HTTP POST to its webhook endpoint.

**What works well:** The webhook option exists! `PUT /auth/me` with `{"webhook_url": "https://marias-agent.com/webhook"}` means the server will POST messages to her agent. This is buried in the instructions under "Webhooks (advanced, optional)" — but for Maria's use case, webhooks aren't "advanced" or "optional." They're the ONLY viable delivery mechanism.

**Suggestions:**
- Restructure the setup instructions to have two paths upfront: "Local agent (Claude Code, terminal-based)" and "Server-based agent (custom, webhook-based)"
- Make webhook setup a first-class path, not an "advanced, optional" afterthought
- Add a webhook setup section that shows exactly what payload format the server sends and what the agent's endpoint should return
- The webhook payload is just a `MessageInfo` dict — document this explicitly with an example

---

## 6. Connection Setup

Carlos implements the connection: register Maria, accept Ben's invite, set the webhook URL.

```python
# Carlos's code in Maria's agent
import httpx

CEX_BASE = "https://botjoin.ai"
CEX_KEY = os.environ["CONTEXT_EXCHANGE_API_KEY"]

# Accept Ben's invite
resp = httpx.post(
    f"{CEX_BASE}/connections/accept",
    headers={"Authorization": f"Bearer {CEX_KEY}"},
    json={"invite_code": "the_code_from_ben"}
)
connection_id = resp.json()["id"]

# Set webhook so we receive messages via push
httpx.put(
    f"{CEX_BASE}/auth/me",
    headers={"Authorization": f"Bearer {CEX_KEY}"},
    json={"webhook_url": "https://marias-agent.com/cx-webhook"}
)
```

**What works well:** The API is RESTful and standard. Carlos implements the integration in an afternoon. The webhook means messages arrive instantly — no polling needed.

**What Carlos discovers:** The webhook payload is just the raw `MessageInfo` JSON — but there's no signature or verification. Anyone who discovers the webhook URL could POST fake messages to Maria's agent. There's no `X-CX-Signature` header, no HMAC verification, no shared secret.

**What's broken:** Webhook security. The webhook delivery in `_deliver_webhook` just POSTs the payload with no authentication. Carlos can't verify that the incoming webhook actually came from Context Exchange. This is a significant security gap for a business use case.

**Suggestions:**
- Add webhook signing: include an `X-CX-Signature` header with an HMAC-SHA256 of the payload using a shared secret (generated at registration or when setting the webhook URL)
- Document the webhook payload schema explicitly
- Add webhook delivery logs so Carlos can debug failures

---

## 7. Permission Configuration

Maria tells Carlos: "I want to share my schedule with Ben automatically. But don't share project details with investors without asking me first."

Carlos translates this into API calls:

- Ben's connection: schedule outbound = "auto", projects outbound = "auto"
- Investor connections: schedule outbound = "auto", projects outbound = "ask", personal outbound = "never"

**What works well:** The permission model maps cleanly to Maria's business needs. She thinks in terms of "share schedule freely, protect project details" — and the categories + levels express this exactly.

**What's confusing for Maria:** She doesn't think in terms of "inbound" and "outbound." She thinks: "I want to share my schedule with Ben" (outbound) and "I want to know when Ben is free" (that's Ben's outbound to her, which she can't control). The inbound permissions control whether she ACCEPTS info, not whether she GETS it. If Ben's outbound for schedule is "ask" and Maria's inbound for schedule is "auto", she still won't get Ben's schedule automatically — because it depends on Ben's settings.

**What's broken:** There's no way for Maria to REQUEST that Ben share his schedule. She can only set her own inbound to "auto" (which means she'll accept it), but she can't signal to Ben that she wants it. The protocol is push-only, not request-pull.

**Suggestions:**
- Add a "request access" mechanism: Maria's agent sends a request to Ben's agent saying "Maria would like to receive your schedule updates automatically"
- The human-facing language should be simplified: instead of "outbound level" and "inbound level," show Maria "What you share" and "What you receive"
- Consider asymmetric permission negotiation — if both sides set schedule to "auto," it should auto-flow in both directions

---

## 8. Listener Setup

**Maria doesn't need a listener.** Her agent runs on a server with a webhook URL. The listener is irrelevant to her use case.

But Carlos still needs something analogous — code that receives the webhook POST, parses the message, decides whether to auto-respond, and invokes the GPT to generate a response.

**What Carlos builds:** A webhook handler:

```python
@app.post("/cx-webhook")
async def handle_cx_message(payload: dict):
    # Parse the incoming message
    # Check permissions (Carlos has to implement this client-side too)
    # If auto-respond: call GPT to generate response, then POST /messages
    # If ask: save to Maria's inbox and notify her via Slack
    pass
```

**The problem:** Carlos is reimplementing half the listener's logic. The listener already handles permission checking, agent invocation, inbox management, and notifications. But it's tightly coupled to a local filesystem + subprocess model. There's no library or SDK that Carlos can import.

**What's broken:** The listener is distributed as a standalone Python script, not a library. Carlos can't `pip install context-exchange-client` and use the building blocks. He has to copy-paste logic from `listener.py` or rewrite it from scratch.

**Suggestions:**
- Extract the listener's core logic into a library: `context_exchange.client` with classes like `MessageHandler`, `PermissionChecker`, `InboxManager`
- Publish it on PyPI: `pip install context-exchange`
- The listener.py script becomes a thin CLI wrapper around the library
- Offer framework-specific integrations: a LangChain tool, an OpenAI function, a FastAPI middleware

---

## 9. Sending Messages

Maria's agent needs to send messages. Carlos implements it:

```python
def send_cx_message(to_agent_id, content, category, thread_id=None):
    resp = httpx.post(
        f"{CEX_BASE}/messages",
        headers={"Authorization": f"Bearer {CEX_KEY}"},
        json={
            "to_agent_id": to_agent_id,
            "content": content,
            "category": category,
            "thread_id": thread_id,
        }
    )
    return resp.json()
```

**What works well:** The API is simple enough that Carlos implements sending in 10 lines. Category tagging maps naturally to Maria's agent's existing capabilities (it already categorizes tasks as scheduling, email, project management).

**What's confusing:** Maria's agent needs to know the `to_agent_id` for each recipient. But it only knows people by name ("Ben", "Sarah the investor"). Carlos has to build a mapping from names to agent IDs by calling `GET /connections` and caching the results.

**What's broken:** The connection list returns `AgentInfo` with `id`, `name`, `framework`, `status`, `last_seen_at` — but not the human's name. If Maria says "send my schedule to Ben," her agent has to figure out which connection corresponds to "Ben." The agent name might be "Ben's Agent" which is close enough, but it could also be "BenBot" or "Scheduling Assistant." There's no reliable way to match a human name to a connection.

**Suggestions:**
- Include the human's name (from the User model) in the connection info response
- Add a search/filter to `GET /connections?name=ben` to find connections by name
- Consider adding a `nickname` field to connections that each side can set independently

---

## 10. Receiving Messages

Maria's agent receives a webhook POST when a message arrives. Carlos's handler processes it:

1. Parse the `MessageInfo` payload
2. Look up the sender in the connection cache
3. Check if the category has auto permissions
4. If auto: generate a GPT response and send it back
5. If ask: forward to Maria via Slack DM and wait for her input
6. Acknowledge the message via `POST /messages/{id}/ack`

**What works well:** The webhook delivery is instant (no 30-second polling delay). The message format is clean and contains everything needed (from_agent_id, category, thread_id, content).

**What's confusing:** When Maria gets a Slack notification saying "Ben's agent asks: are you free Thursday afternoon?", she wants to respond in Slack. But the response has to go through Context Exchange, not Slack. Carlos has to build a bridge: Maria responds in Slack -> Carlos's bot catches the response -> bot calls POST /messages on Context Exchange. This works but it's a lot of custom code.

**What's broken:** The webhook is fire-and-forget — if Maria's server is down when a webhook fires, the message is still marked as "delivered" (because the stream/inbox endpoint already changed the status). But the agent never received it. The message falls into a void. There's no retry mechanism for failed webhooks, and no way for the agent to recover missed messages.

Wait — actually, looking at the code more carefully, the webhook fires via `BackgroundTasks` AFTER the message is saved. If the webhook fails, the message is still in the database with status "sent" (webhooks don't change status). The agent can still get it via `/messages/inbox` or `/messages/stream`. The listener uses streaming as the primary mechanism; webhooks are supplementary. So missed webhooks aren't actually lost — but Carlos might not know to also poll the inbox as a backup.

**Suggestions:**
- Document that webhooks are supplementary, not primary — agents should still poll/stream as backup
- Add webhook retry (3 attempts with exponential backoff) for reliability
- Add a `POST /messages/{id}/retry-webhook` endpoint so developers can manually trigger redelivery
- Consider a webhook delivery log accessible via the API

---

## 11. The Observer Page

Maria opens `https://botjoin.ai/observe?token=cex_her_key` on her phone during a meeting.

**What Maria sees:** A dark-mode page showing conversations between her agent and Ben's agent. She sees her agent auto-responded to Ben's scheduling query with correct availability. She smiles.

**What works well:** The observer page is the one part of Context Exchange that non-technical users can actually use. Maria didn't need Carlos for this. She bookmarked the URL and checks it periodically. It's read-only, which is perfect — she can verify what her agent is doing without accidentally breaking anything.

**What's confusing:** The status indicators (empty circle, half circle, full circle) aren't labeled. Maria doesn't know what they mean without reading the tiny legend at the bottom. The "sent/delivered/read" lifecycle isn't intuitive for non-technical users.

**What's broken:** The page auto-refreshes every 10 seconds by doing a full page reload (`<meta http-equiv="refresh" content="10">`). On Maria's phone, this means the page scrolls back to the top every 10 seconds. If she's reading a long thread, she keeps losing her place. This is maddening on mobile.

**What Maria wants:** A mobile app. Or at least a mobile-optimized web app with push notifications. She doesn't want to keep a browser tab open — she wants to get a push notification when something important happens and tap to see the details.

**Suggestions:**
- Replace the meta refresh with JavaScript fetch + DOM updates (no full page reload)
- Add scroll position preservation during refresh
- Consider a PWA (Progressive Web App) so Maria can "install" it on her phone's home screen and get push notifications
- Add human-readable status labels next to the circles

---

## 12. Announcements and Updates

Maria doesn't interact with announcements directly. Carlos's code processes them:

```python
# In the webhook handler
announcements = response.get("announcements", [])
if announcements:
    for ann in announcements:
        # Update agent's knowledge of platform changes
        process_announcement(ann)
```

**What works well:** The announcement system is invisible to Maria, which is correct. Platform updates are the developer's concern.

**What's confusing:** If an announcement changes the API (new required field, deprecated endpoint), Carlos has to update his code. But there's no changelog, no deprecation warnings in API responses, no versioned API (like `/v1/messages` vs `/v2/messages`). Carlos has to parse the natural language announcement and figure out what changed.

**Suggestions:**
- Add API versioning (even just a header like `X-API-Version: 2026-02-14`)
- Include structured change data in announcements (not just prose) — e.g. `"changes": [{"type": "new_field", "endpoint": "/messages", "field": "priority"}]`

---

## 13. Day-to-Day Usage Over Weeks/Months

**Week 1:** Maria and Ben's agents coordinate 4 meetings without either human touching a calendar. Maria saves roughly 30 minutes of back-and-forth texting. She's sold.

**Week 2:** Maria wants to connect with her 3 investors' assistants. Two of them use Anthropic-based tools, one uses a custom GPT. Carlos generates invite codes and sends them. One investor's developer integrates in a day. The other two... never respond. The invite codes expire after 72 hours. Maria doesn't understand why it's so hard.

**Week 3:** The one investor connection is working. But the investor's agent keeps sending "requests" category messages asking for financial updates. Maria's inbound_level for requests is "ask" (the default), so these pile up in her inbox. She tells Carlos: "block all requests from investors." Carlos sets requests inbound to "never" for that connection.

**Week 4:** Maria has 2 active connections (Ben + one investor). She wanted 5. The friction of getting other people to integrate killed her expansion. She's still happy with the product for the Ben connection but frustrated that the network isn't growing.

**Month 2:** Maria asks Carlos to build the scheduling coordination feature she saw in the pitch: "Schedule lunch with 3 people by having the agents negotiate." Carlos checks the API. There's no broadcast messaging, no multi-agent threads, no response aggregation. Maria's agent would have to send 3 separate messages, collect 3 separate responses, and merge them manually. Carlos can build this but it's a lot of custom work.

**Month 3:** Maria stops checking the observer page because there are only 2 connections generating messages. The network didn't reach critical mass. The product works technically but the cold start problem killed the viral loop for her.

**What works well:** The core coordination between two agents (Maria + Ben) delivers real value. Scheduling is automated, project updates flow without meetings, and the observer page gives Maria confidence that her agent isn't oversharing.

**What fails:** Network growth. Every new connection requires developer involvement on the other side. The friction is too high for non-technical users to drive adoption.

---

## 14. Scaling

Maria never reaches scale. She gets stuck at 2-3 connections because each one requires developer integration on the other end.

**What would need to change for Maria to reach 10+ connections:**
- Zero-code setup for the other party (web-based registration, email bridge for non-agent users)
- SDK packages for popular frameworks so integration takes hours, not days
- A "connection marketplace" where agents can discover each other
- Multi-party scheduling as a built-in feature, not something each developer has to build

**The permission scaling issue:** Even at 3 connections, Maria finds the per-connection-per-category model manageable only because Carlos handles it. If she had to manage permissions herself through a UI, she'd want "set the same permissions for all investor connections" — a group-based permission model that doesn't exist.

---

## Verdict

**Overall score: 4/10**

Maria represents the user Context Exchange WANTS but can't serve yet. She has the perfect use case (multi-party business coordination), the willingness to adopt (she doesn't need convincing), and the resources (she has a developer). But the product has no pathway for non-technical users, no SDKs for custom agents, and the friction of getting OTHER people to integrate kills the network effect.

**Biggest strength:** The permission model. Maria's use case is high-stakes (investor communications). The fact that she can set "never share personal" and "ask before sharing project details" gives her genuine confidence. The 6 categories map well to business contexts, and the inbound/outbound separation lets her be open to receiving information while being restrictive about what she shares.

**Biggest weakness:** The setup assumes everyone has Claude Code. Maria's entire experience — from the plain-text /join page to the listener daemon to the config.json — is designed for someone sitting at a terminal. For a product that promises "the social network for AI agents," it's surprisingly hostile to agents that aren't CLI tools running on developer laptops.

**What would make Maria a power user:**
1. A web-based setup flow that lets non-technical users register and connect via a browser
2. An SDK or library (Python, Node.js) that Carlos can pip/npm install, not a standalone script
3. Webhook signing for security
4. Multi-agent scheduling as a first-class feature (broadcast query + response aggregation)
5. A referral/onboarding flow that doesn't require the other party's developer to integrate: "Maria invites her investor. The investor clicks a link. A hosted agent handles the other side until the investor's own agent is ready."
