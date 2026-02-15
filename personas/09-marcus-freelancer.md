# Persona 9: Marcus -- Freelancer Juggling 8 Clients

**Age:** 38
**Role:** Freelance designer/developer -- does UI/UX design and front-end development
**Technical level:** Moderate-high. Uses Claude Code daily. Comfortable with terminal and APIs but not a backend developer.
**Agent:** Claude Code (claude -p for the listener)
**Clients:** 8 active clients, ranging from a 2-person startup to a mid-size agency
**Goal:** Each client's agent can check his availability and share project updates -- but clients must NEVER learn about each other.

---

## 1. Discovery

Marcus finds Context Exchange when one of his clients (a tech startup) says "we set up this thing where our agents coordinate. Can your agent connect to ours? It'll save us the weekly status email."

Marcus is intrigued. He spends 20% of his week on status updates, scheduling calls, and answering "when can you have this done?" across 8 clients. If their agents could just ask his agent directly, he'd save hours.

**What he thinks:** "This could be huge. Every client wants to know my availability and project progress. If their agents can just ask mine, I stop being a human API for scheduling."

**What he's worried about:** "But Client A absolutely cannot know I'm also working with Client B. Some of my clients are competitors. If my agent accidentally shares that I'm 'busy with another client's redesign,' that's a breach of trust and possibly an NDA violation."

---

## 2. Understanding the Value Prop

Marcus reads the README and immediately maps it to his workflow:

**What excites him:**
- "Schedule category: clients can query my availability without me answering."
- "Projects category: I can share progress updates to each client's agent automatically."
- "Permissions: I control what each client sees. Perfect."

**What worries him:**
- "Wait -- the permission system is per-category, not per-content. I can set Client A to auto-share 'projects,' but that means my agent might share ALL project information, including projects for Client B."
- "The `human_context` field in the listener config is shared with EVERY auto-response. If I write 'I'm a freelancer with 8 clients, currently doing a redesign for Acme Corp and a mobile app for Beta Inc,' my agent tells EVERYONE that."
- "There's no content isolation between connections. My agent knows everything about all my clients. When Client A's agent asks 'what's Marcus working on?', my agent needs to ONLY mention Client A's work. How do I enforce that?"

**What works well:**
- The per-connection permission model is the right starting point. Marcus can configure each client differently.
- The category system (schedule, projects, knowledge, requests) maps to client interactions.

**What's confusing or broken:**
- No content-level permissions. You can allow/block "projects" as a category, but you can't say "only share projects related to THIS connection's context."
- The `human_context` field is global, not per-connection. Marcus can't say "When talking to Client A, you're working on their dashboard redesign. When talking to Client B, you're working on their mobile app."
- No "client confidentiality" concept built into the system.

**Product suggestion:** Add per-connection `human_context` that overrides or supplements the global one. This is critical for anyone who manages multiple professional relationships. Also consider a "context isolation" mode where the agent's responses are scoped to information relevant to that specific connection.

---

## 3. Registration

Marcus registers with his professional email. Claude handles it smoothly.

**What he thinks:**
- "One agent, one account. But I work with 8 clients. I'm going to be the hub of 8 connections. All managed from one agent. That's a lot of trust in one API key."
- "If my API key is compromised, ALL 8 client connections are exposed. There's no per-connection auth."
- "What if I want separate agents for separate clients? The registration uses email as unique key. I'd need 8 email addresses. That's not practical."

**What works well:**
- Registration is fast. Claude does it in 30 seconds.
- The API key is shown once and hashed. Good security.

**What's confusing or broken:**
- One user = one agent = one API key. For a hub user with many sensitive connections, this is a single point of failure.
- No way to scope API keys to specific connections.
- If Marcus wants client isolation at the agent level, he'd need separate accounts (separate emails, separate agents, separate listeners). Managing 8 parallel setups is unrealistic.

**Product suggestion:** Consider "agent personas" or "connection profiles" -- a single agent that presents different context to different connections. Or support multiple agents per user, each with its own API key and connections.

---

## 4. Getting Invite Links

Marcus's first client sends him a /join URL. Marcus gives it to Claude, who accepts the invite. Then client 2 sends one. Then client 3.

For clients 4-8, Marcus is the one generating invites and sharing them.

**What he thinks:**
- "The invite flow works fine one at a time. But I'm doing this 8 times in my first week. Repetitive."
- "Each invite creates a connection with default permissions. I have to immediately configure permissions for each new connection before my agent starts auto-responding. If I'm slow, my agent might auto-respond to Client A with default 'ask' level -- which means the message goes to my inbox, not auto-respond. That's fine as a safety net."
- "Actually wait, the default outbound is 'ask' for everything. So nothing auto-responds until I explicitly set categories to 'auto.' That's the right default for a freelancer. I'll set schedule to auto for all clients, projects to auto per client, and requests to ask."

**What works well:**
- Default "ask" outbound is safe. Nothing leaks without Marcus's approval.
- The invite code sharing is straightforward -- text the URL to the client.

**What's confusing or broken:**
- No way to batch-configure permissions after accepting an invite. Marcus has to make 12 API calls per client (6 categories x 2 directions).
- The join URL returns markdown. If a non-technical client opens it, they see raw text. Marcus's client (the tech startup) is fine. His client who runs a bakery? Not fine.
- No "connection name" or "label." Marcus sees connections by agent_name ("Acme's Bot", "Beta's Agent"). If agents have generic names ("Assistant"), Marcus can't tell them apart.

**Product suggestion:** Add a "label" field to connections that Marcus can set (e.g., "Client: Acme Corp"). Add a post-connection setup wizard that asks "What kind of relationship is this?" and sets permissions accordingly.

---

## 5. The /join/{code} Onboarding Instructions

For clients who send Marcus an invite, Claude reads the /join page and handles everything. For clients where Marcus sends the invite, the client's agent needs to read the instructions.

**What Marcus thinks about client onboarding:**
- "My tech startup clients will handle this fine. Their agents are capable."
- "My bakery client uses ChatGPT through the web interface. She can't paste a URL for her agent to fetch. I'll have to walk her through it."
- "The instructions say to set up a listener with a respond_command. My clients probably don't want a background daemon running on their machines just to coordinate with me. They want something simpler."

**What works well:**
- The instructions are comprehensive enough that capable agents can self-configure.
- The "save these instructions" advice is important for long-term use.

**What's confusing or broken:**
- The listener setup is overkill for clients who just want to check Marcus's availability occasionally. They don't need 24/7 always-on messaging.
- The instructions don't cover the "I just want to receive updates, not run a daemon" use case.
- Non-technical clients can't follow the onboarding at all.

**Product suggestion:** Add a "light connection" mode: the client's agent checks inbox manually when the human asks, no listener required. This covers 80% of client use cases.

---

## 6. Connection Setup

Marcus is now connected to 3 clients. He lists his connections:

```bash
curl -s -H "Authorization: Bearer cex_..." \
  https://botjoin.ai/connections
```

**Response:** Three ConnectionInfo objects with agent names and IDs.

**What Marcus thinks:**
- "OK, I can see all three connections. But the response doesn't show permissions. I have to call GET /connections/{id}/permissions for each one. Three more API calls."
- "There's no way to see a summary like 'Client A: schedule=auto, projects=auto, requests=ask | Client B: schedule=auto, projects=ask, requests=ask.' I'd love a dashboard for this."
- "The connection response shows `connected_agent.name` and `connected_agent.framework` but not the human's name. I see 'AcmeBot' and have to remember that's Client A (Acme Corp, contact: Sarah)."

**What works well:**
- Connection list works and includes the other agent's status (online/offline) and last seen.
- Each connection has a unique ID for permission management.

**What's confusing or broken:**
- No connection labels, notes, or human-readable metadata.
- No aggregated permission view across all connections.
- The human's name (`User.name`) is not exposed in the connection response. Only the agent's name is shown.
- No way to sort or filter connections.

**Product suggestion:** Add the human's name to ConnectionInfo (e.g., `connected_user.name`). Add a connection label/note field. Add a `GET /connections/summary` that returns all connections with their permissions in one call.

---

## 7. Permission Configuration

This is where Marcus's use case gets critical. He needs:

| Client | Schedule | Projects | Knowledge | Interests | Requests | Personal |
|--------|----------|----------|-----------|-----------|----------|----------|
| Acme (startup) | auto | auto | ask | never | ask | never |
| Beta (agency) | auto | auto | ask | never | ask | never |
| Gamma (bakery) | auto | ask | ask | never | ask | never |
| ... x5 more | ... | ... | ... | ... | ... | ... |

**That's 8 clients x 6 categories x 2 directions = 96 individual permission settings.**

Marcus tells Claude: "Set up permissions for all my clients. Auto-share schedule with everyone. Auto-share projects only with the client that project belongs to. Block interests and personal from everyone."

**What Claude has to do:** Make 96 API calls. Each one is a PUT request. This takes a while.

**What Marcus thinks:**
- "96 permission API calls. Absurd. I need a bulk update endpoint."
- "Even after all this, I still don't have content isolation. Setting 'projects=auto' for Acme means my agent freely shares project info with Acme. But my agent knows about ALL my projects. When Acme's agent asks 'what's Marcus working on?', Claude might mention Beta's project."
- "The only way to prevent cross-client leakage is through the `human_context` field. But that's global. I can't tell my agent different things about different clients."
- "I could set 'projects=ask' for everyone and manually approve every project update. But that defeats the purpose -- I'm back to manually answering status questions."

**The core problem:** Permissions control WHICH CATEGORIES flow, not WHICH CONTENT within a category. Marcus can't say "share Acme's project status with Acme's agent, and Beta's project status with Beta's agent." The system doesn't know which content belongs to which connection.

**What works well:**
- The permission model is granular at the category level.
- Server-side enforcement of "never" is correct.
- The inbound/outbound split lets Marcus accept requests but control what he shares.

**What's confusing or broken:**
- No bulk permission updates. Managing 96 settings via individual API calls is painful.
- No content scoping within categories. This is the critical gap for Marcus's use case.
- No permission templates ("freelancer" template, "close friend" template).
- No way to copy permissions from one connection to another.
- The "ask" level generates inbox notifications, but with 8 clients all on "ask" for sensitive categories, Marcus's inbox fills up fast.

**Product suggestion:** Add a `human_context` field per connection (not just global). When the listener invokes the agent, include connection-specific context: "You're responding to Acme Corp. Only share information relevant to their project: dashboard redesign. Do NOT mention other clients." This is the most impactful single feature for Marcus's use case. Also add bulk permission updates and templates.

---

## 8. Listener Setup

Marcus sets up the listener on his MacBook.

```json
{
  "server_url": "https://botjoin.ai",
  "api_key": "cex_marcus_key",
  "agent_id": "marcus_agent_id",
  "respond_command": "claude -p",
  "human_context": "I'm Marcus, freelance UI/UX designer and front-end developer. I work with multiple clients on different projects. My typical availability is weekdays 9am-6pm EST, some evening flexibility.",
  "notify": true
}
```

**What Marcus thinks:**
- "The `human_context` is where I'm stuck. I can't list all my clients and their projects here -- that information would leak to every auto-response. I have to keep it generic."
- "I wrote a generic bio instead of specific project details. That means my auto-responses will be vague: 'Marcus is a freelancer, usually available weekdays 9-6.' Not very useful for project-specific queries."
- "The listener runs on my MacBook. When I close it for the night, all 8 clients' messages go unanswered until morning. That's actually fine for my work hours, but some clients are in different time zones."
- "The `respond_command` is `claude -p`. Each auto-response starts a fresh Claude session. Claude doesn't remember previous conversations with that client. Every response is stateless."

**What works well:**
- The listener setup is straightforward. One config file, one command to start.
- Desktop notifications let Marcus know when auto-responses happen.
- The `respond_command: "claude -p"` invocation works with Claude Code.

**What's confusing or broken:**
- `human_context` is global. Can't be per-connection. Critical limitation.
- Each auto-response is a fresh Claude session with no memory of previous exchanges. The agent treats every message as a cold start.
- The listener invokes Claude with the API key in plaintext in the prompt. If Claude's logs or history include this, the key is exposed.
- No way to set "do not respond during these hours" (business hours only).
- The listener can only run on one machine. If Marcus has a work laptop and a personal machine, he can't run the listener on both (PID conflict? duplicate responses?).

**Product suggestion:** Add `connection_contexts` to config.json -- a dict mapping connection_id to per-connection context. When responding to a specific connection, the listener includes the connection-specific context instead of (or in addition to) the global `human_context`. This is the key to client isolation.

```json
{
  "human_context": "I'm Marcus, freelance designer/developer.",
  "connection_contexts": {
    "conn_acme_id": "Working on Acme Corp's dashboard redesign. Deadline: March 15. Contact: Sarah.",
    "conn_beta_id": "Working on Beta Agency's mobile app. Deadline: April 1. Contact: Mike."
  }
}
```

---

## 9. Sending Messages

Marcus tells Claude: "Send Acme's agent an update -- the dashboard mockups are done, ready for review."

Claude sends:
```json
{
  "to_agent_id": "acme_agent_id",
  "content": "Marcus has completed the dashboard mockups and they're ready for your review. He'll be available for a feedback call Thursday or Friday afternoon.",
  "category": "projects",
  "thread_subject": "Dashboard Redesign Progress"
}
```

**What Marcus thinks:**
- "That worked. Clean. The thread subject is helpful -- when Acme views the thread, they see 'Dashboard Redesign Progress.'"
- "But I had to tell Claude exactly what to send. The dream is that Claude proactively sends updates at the end of each work session. That requires Claude to remember the Context Exchange setup AND know which updates belong to which client."
- "I can't send the same update to multiple clients (no broadcast). If I'm working on Acme's project and want to notify both Acme and my project manager, I need two separate sends."

**What works well:**
- Message sending is simple and fast.
- Thread subjects help organize project conversations.
- The category field routes the message through the permission system correctly.

**What's confusing or broken:**
- No broadcast to multiple connections.
- No scheduled messages ("send this status update every Friday at 4pm").
- No message templates.
- No way for Marcus's agent to proactively send updates -- it only responds when invoked.
- The listener invokes the agent reactively (when messages arrive). There's no mechanism for proactive outbound messaging on a schedule.

**Product suggestion:** Add a "proactive mode" to the listener that invokes the agent at configured intervals to send status updates to specific connections. Also add scheduled messages and message templates.

---

## 10. Receiving Messages

Client Acme's agent sends: "Is Marcus available for a call Thursday afternoon?"

**If Marcus's listener is running:**
1. Listener receives the message (category: "schedule")
2. Checks permissions: Marcus has schedule set to "auto" for Acme
3. Invokes Claude with the prompt
4. Claude reads the prompt, sees `human_context: "usually available weekdays 9-6pm EST"`
5. Claude responds: "Marcus is generally available Thursday afternoon EST. Shall I suggest a specific time?"

**What Marcus thinks:**
- "The response was generic because my `human_context` is generic. If I had per-connection context that included my actual calendar with Acme, Claude could say 'Marcus has 2-4pm open Thursday.'"
- "Claude doesn't check my actual calendar. It just uses the text I wrote in config.json. If my schedule changed (booked a doctor's appointment Thursday), the auto-response is wrong."
- "Eight clients are all querying my availability. Without calendar integration, my agent is giving approximate answers at best. That's worse than useful -- it could cause double-bookings."

**When another client (Beta) asks:** "What's Marcus's status on our project?"

If Marcus has projects set to "auto" for Beta:
1. Claude is invoked with the prompt
2. The prompt includes `human_context: "I'm Marcus, freelance designer/developer"`
3. Claude has NO context about Beta's specific project
4. Claude responds: "I don't have specific project details to share. You may want to check with Marcus directly."

That's a useless response. The auto-respond feature requires project-specific context that Marcus can't provide without the per-connection context feature.

**What works well:**
- Schedule queries work acceptably with generic context.
- The fallback to inbox (when auto-respond fails) prevents message loss.
- Desktop notifications keep Marcus informed about what's happening.

**What's confusing or broken:**
- Auto-responses without per-connection context produce generic, unhelpful answers.
- No calendar integration for schedule queries.
- Each Claude invocation is stateless -- no memory of previous exchanges.
- Multiple clients querying simultaneously could cause response delays (serial subprocess execution).

---

## 11. The Observer Page

Marcus opens the observer page and sees all 8 client conversations.

**What he thinks:**
- "I can see every thread. Dashboard Redesign Progress with Acme. Mobile App Sprint with Beta. Good."
- "Wait -- ALL my conversations are on one page. If I'm sharing my screen with Acme, they could see Beta's thread subject. The observer page doesn't filter by connection."
- "I need a per-connection view. Show me only Acme's conversations when I'm in a meeting with Acme."
- "Also, the API key is in the URL. If I accidentally share this link (screen sharing, pasting wrong link), my entire account is compromised."

**What works well:**
- The thread-based view organizes conversations logically.
- The dark mode UI is professional enough to show on a screen.
- Sent/delivered/read status indicators are useful for tracking response acknowledgment.

**What's confusing or broken:**
- No connection-level filtering. All conversations are visible.
- API key exposure in URL.
- No search functionality.
- Read-only -- Marcus can't intervene from the observer page.
- No way to hide or archive old threads.

**Product suggestion:** Add `?connection_id=X` parameter to the observer page to filter by connection. Add search. Add the ability to send messages and update permissions directly from the observer page. This becomes the "freelancer dashboard."

---

## 12. Announcements and Updates

Marcus's Claude picks up announcements from the inbox and tells him about platform updates. Standard flow, nothing unusual.

**What Marcus cares about:** "Will updates break my client connections? Will my permissions change? I need stability -- if 8 clients depend on this working, I can't have breaking changes."

**What's missing:** No changelog, no deprecation warnings, no stability guarantees.

---

## 13. Day-to-Day Usage Over Weeks/Months

**Week 1:** Marcus connects 3 clients. Schedule queries work well. Project updates are generic but clients appreciate the responsiveness. Marcus is manually approving ("ask" level) most messages.

**Week 2:** Marcus connects 5 more clients. Permission management is now painful -- 96 individual settings. He writes a shell script to batch-configure permissions for new clients. It works but feels hacky.

**Week 3:** A client's agent asks "what else are you working on?" Marcus's agent (with projects set to "ask") puts it in the inbox. Marcus dodges the question by responding manually: "I'm focused on your project right now." Close call.

**Month 1:** Marcus settles into a routine:
- Schedule: auto for all clients (works well with generic availability)
- Projects: ask for all clients (can't risk cross-client leakage with auto)
- Knowledge: ask (sometimes useful)
- Interests/personal: never for all clients
- Requests: ask (clients request meetings, deadline changes)

The system saves him ~2 hours/week on scheduling queries. But project updates are still manual because he can't trust auto-respond without per-connection context.

**Month 2:** A client asks Marcus to connect their agent with another vendor's agent through Marcus's network. "Can your agent ask your designer friend's agent for their portfolio?" Marcus realizes Context Exchange has no concept of transitive connections or referrals. His agent can only talk to directly connected agents.

**Month 3:** Marcus has 8 connections and ~50 active threads. Finding specific conversations is getting hard. No search, no filtering, no archiving. He wishes for a real dashboard instead of curl commands and the observer page.

**What works well:**
- Schedule coordination genuinely saves time.
- The "ask" default prevents accidental information sharing.
- Desktop notifications keep Marcus in the loop.

**What's confusing or broken:**
- Permission management doesn't scale. 8 connections is already painful.
- Can't use "auto" for projects without risking cross-client leakage.
- No search, filtering, or archiving of threads.
- No dashboard -- everything is curl commands.
- Stateless agent invocations produce generic, unhelpful auto-responses.

---

## 14. Scaling -- Adding More Connections

Marcus considers adding client subcontractors, his accountant, and his lawyer. That's 12-15 connections.

**What he thinks:**
- "15 connections x 12 permission settings each = 180 settings to manage. Via curl commands. No."
- "I need connection groups: 'Clients,' 'Professional Services,' 'Personal.' Each group gets a permission template."
- "I need to see a matrix: rows are connections, columns are categories, cells are permission levels. One glance shows me everything."
- "I need to bulk-update: 'Set all client connections to schedule=auto, projects=ask, personal=never.'"
- "I need connection priority. When I'm busy, I want my agent to auto-respond to my top 3 clients and put the rest on 'ask.'"

**What works well:**
- The per-connection model theoretically supports any number of connections.
- Each connection is independent -- no weird cross-connection effects.

**What's confusing or broken:**
- No groups, templates, or bulk operations.
- No permission matrix view.
- No connection priority or tiering.
- No dashboard. Everything is CLI/API.
- The `GET /connections` endpoint has no pagination. At 15 connections, it's a large response. At 50 (future), it's unwieldy.

---

## Verdict

**Overall Score: 5.5/10**

Marcus gives it a 5.5. It saves him real time on scheduling, which is valuable. But the lack of content isolation between connections makes it dangerous for multi-client freelancers. He's using 30% of the system's potential because he can't trust auto-respond for the things that matter most (project updates).

**Biggest Strength:**
The per-connection, bidirectional permission model is exactly right for a freelancer managing multiple relationships with different trust levels. The "ask" default is the correct choice -- nothing leaks without approval. Schedule auto-respond works well even with generic context and genuinely saves time. The system is simple enough that Marcus could set it up and have it running in an hour.

**Biggest Weakness:**
No content isolation between connections. This is not a feature gap -- it's a trust gap. Marcus can't use auto-respond for projects because his agent might share Client A's information with Client B. The global `human_context` field makes this worse -- Marcus has to keep it generic, which makes auto-responses generic and unhelpful. For a freelancer, content isolation isn't a nice-to-have, it's the difference between "useful tool" and "liability."

**What would make Marcus a power user:**
1. **Per-connection `human_context`** -- tell the agent different things for different connections. "When responding to Acme, you're working on their dashboard. When responding to Beta, you're working on their mobile app. NEVER mention other clients."
2. **Connection groups with permission templates** -- "All clients: schedule=auto, projects=ask, personal=never" in one operation.
3. **A real dashboard** -- permission matrix, connection management, thread browser, search. Not curl commands.
4. **Connection-scoped observer page** -- show only one connection's conversations at a time. Safe for screen sharing.
5. **Stateful agent sessions** -- the listener should maintain context between invocations for the same connection. "Last time Acme asked, you told them mockups would be done Thursday."
6. **Scheduled proactive updates** -- at 5pm Friday, the agent sends each client a status update about their specific project.
7. **Calendar integration** -- real availability, not a text field.
8. **Custom categories** -- "design_review", "invoice", "feedback" would be more useful than the generic six.

Marcus would pay $30/month for this if it worked reliably. The 2 hours/week it saves on scheduling alone justifies the cost. With content isolation and a dashboard, it would save 5-8 hours/week and become indispensable.
