# Persona 7: Sophie & Tom -- Couple Coordinating Daily Life

**Sophie:** 32, product manager, uses Claude Code through her terminal daily
**Tom:** 34, high school teacher, uses ChatGPT with a custom wrapper his friend built
**Kids:** Two -- ages 4 and 7
**Technical level:** Sophie is dev-adjacent (comfortable with terminal, not a coder). Tom is purely non-technical (the wrapper was set up for him).
**Goal:** Their agents coordinate grocery lists, dinner plans, kid pickup, weekend activities, and household tasks -- automatically, every day.

---

## 1. Discovery

Sophie hears about Context Exchange from a developer friend at work. He says "my agent and my wife's agent coordinate our schedules now, it's insane." Sophie's ears perk up because she and Tom spend 30+ texts a day on pure logistics: "Can you grab milk?" "Who's picking up Lily?" "What are we doing Saturday?"

Tom hears about it from Sophie, who says "I found this thing where our AI assistants can talk to each other. Like, my Claude can ask your ChatGPT if you're free, and you never have to answer." Tom's reaction: "That sounds cool but also kind of creepy?"

**What works:** The pitch lands perfectly for this use case. "Your agent talks to your friend's agent" is exactly what Sophie wants. The "no humans needed for scheduling" angle is the killer hook for a couple who texts constantly about logistics.

**What's confusing:** Tom immediately wonders about privacy. "So my ChatGPT tells your Claude everything?" Sophie has to reassure him there are permission levels. But she hasn't set it up yet and can't explain exactly how it works.

---

## 2. Understanding the Value Prop

Sophie reads the README. She understands the flow: register, connect, set permissions, start the listener.

**What she thinks:**
- "OK, the curl command examples are... a lot. I use the terminal but I don't want to copy-paste 10 curl commands."
- "Six categories: schedule, projects, knowledge, interests, requests, personal. Where does 'pick up Lily from daycare at 3:30' go? That's schedule. Where does 'we need milk and eggs' go? That's... requests? Knowledge? There's no 'groceries' category."
- "The README says 'Prerequisites: Python 3.9+, an AI agent (Claude Code, OpenClaw, or any agent with a CLI).' Tom doesn't have Claude Code. His ChatGPT wrapper is a web thing his friend made. Does that count as 'any agent with a CLI'?"

Tom glances at the README over Sophie's shoulder: "I don't understand any of this." He sees curl commands and checks out immediately.

**What works well:**
- The high-level explanation ("Instead of texting your friend 'are you free Friday?', your agent asks their agent directly") is clear and motivating.
- The "How it works" four-step overview is digestible.

**What's confusing or broken:**
- The README is developer-oriented. There's no "for regular people" section. Sophie can handle it; Tom cannot.
- The six categories don't map to daily couple life. They need: groceries, meal planning, kid logistics, household chores, social plans, finances. The existing categories are too abstract.
- Tom's ChatGPT wrapper likely can't run the listener (it's a web-based tool, not a CLI). The "any agent with a CLI" requirement excludes a huge segment of potential users.
- No mention of how two different AI platforms (Claude vs ChatGPT) interoperate. They just exchange text messages through the API, which is framework-agnostic, but the README doesn't reassure non-technical users about this.

**Product suggestion:** Add a "Common Use Cases" section with a couple/family example. Show exactly how "pick up Lily at 3" maps to the category system. Add a "Getting started without a CLI" guide for web-based agents.

---

## 3. Registration

Sophie registers herself. She opens her terminal and tells Claude: "Set me up on Context Exchange." She pastes the /join URL her developer friend gave her (for demo purposes) or navigates to the /setup instructions.

Claude reads the instructions, asks her three questions, and registers. This goes smoothly because Claude Code can make HTTP calls.

**Sophie's experience:** "That was actually easy. Claude asked my name, email, and what to call itself. Done."

Tom's experience is harder. His ChatGPT wrapper doesn't have native tool use for HTTP calls. His friend set it up with a specific set of functions, and "make arbitrary API calls" isn't one of them. Options:
1. Tom's friend updates the wrapper to support Context Exchange (unlikely -- he's busy)
2. Tom registers manually via curl (he can't)
3. Sophie registers for Tom and gives him the API key (viable but she's now managing two accounts)

**What works well:**
- For Claude Code users, registration through the /join flow is genuinely smooth. The agent reads the instructions, asks questions, and handles everything.
- The API key being shown once creates urgency to save it. Good security practice.

**What's confusing or broken:**
- Tom is stuck. The entire product assumes "your agent can make HTTP calls." ChatGPT through a web wrapper typically can't. This is the biggest adoption barrier for non-technical users.
- No web registration form. Everything is API-only. For a product that wants mainstream adoption, this is a gap.
- Sophie could register Tom's account, but then she has his API key. There's no way to transfer or rotate keys. If they ever have a conflict, Sophie controls both accounts.
- No password. No 2FA. Just an email and API key. If Sophie registers with Tom's email, Tom can't register separately later (409 conflict).

**Product suggestion:** Build a simple web registration form at `/register`. Even a bare HTML form that calls the API and displays the key would help enormously. This is the single highest-impact feature for non-technical adoption.

---

## 4. Getting an Invite Link / Sharing One

Sophie's agent generates an invite: `POST /connections/invite`. Claude tells Sophie: "Here's an invite link for Tom. Share it with him."

Sophie texts Tom the link. Tom... doesn't know what to do with it. He opens it in his browser and sees a wall of markdown text starting with "Context Exchange -- Agent Setup Instructions." It's written for an AI agent to read, not a human.

**What Tom sees:** Technical instructions about curl commands, API keys, and config files. He closes the tab.

**What Sophie has to do:** She copies the invite code, walks to Tom's computer, and either:
- Feeds the /join URL to Tom's ChatGPT wrapper (if it can fetch URLs -- maybe)
- Manually registers Tom and accepts the invite on his behalf

**What works well:**
- The /join URL concept is brilliant: one link contains everything an agent needs.
- Single-use + expiry prevents abuse.

**What's confusing or broken:**
- The /join URL returns plaintext markdown. When a human opens it in a browser, they see raw markdown -- not a rendered page, not a human-friendly landing page. For a "magic link" that's supposed to be shared between friends, this is terrible UX.
- The entire connection flow assumes both parties have agents that can make API calls. In a couple where one person is non-technical, this falls apart.
- No way to accept an invite from a web browser. No human-facing accept flow.

**Product suggestion:** Make `/join/{code}` return a rendered HTML page when accessed from a browser (detect `Accept: text/html` header). Show a human-friendly page that says "Sophie invited you to connect on Context Exchange. Here's what that means. To get started, give this link to your AI agent." The raw markdown is returned when an agent fetches it (detect `Accept: text/plain` or non-browser user agents).

---

## 5. The /join/{code} Onboarding Instructions

Assuming Sophie gets Tom's agent to read the /join instructions:

**What Claude Code does (Sophie's side):** Follows the instructions perfectly. Registers, accepts invite, sets up config, downloads listener, starts it. Sophie answers three questions and is done.

**What Tom's ChatGPT wrapper does:** Depends entirely on the wrapper's capabilities. Best case: it can make HTTP calls and follows the instructions. Worst case: it can't make HTTP calls and the instructions are useless.

**What works well for agents that can follow instructions:**
- The instructions are comprehensive and well-structured. Claude Code handles them flawlessly.
- The step-by-step flow (register, verify, accept invite, set up listener) is logical.
- The permission configuration questions are good: "Should I respond on my own? For which topics?"

**What's confusing or broken:**
- Step 5 (listener setup) asks the human a third round of questions: "Tell me about yourself," "Should I respond on my own," "What command to invoke you." For Sophie, this is fine. For Tom through his limited wrapper, these questions may not even reach him properly.
- The `respond_command` question assumes a CLI agent. Tom's ChatGPT wrapper doesn't have a CLI. What does he put for `respond_command`? The instructions don't cover web-based agents.
- The listener daemon requires Python 3 and runs on Unix. Tom might be on a Chromebook or iPad.

**Product suggestion:** Add a "web agent" path in the onboarding that doesn't require the listener at all. Instead, the agent polls `/messages/inbox` during active conversations. Not always-on, but covers the 90% case where both people are awake and chatting.

---

## 6. Connection Setup

Assuming Sophie handles both sides of the setup, the connection is created.

**What Sophie thinks:** "OK, we're connected. Now what? How do I tell my agent to ask Tom's agent about dinner?"

**What she tries:** She tells Claude: "Ask Tom's agent what he wants for dinner tonight." Claude needs to:
1. Know it's connected to Tom's agent on Context Exchange
2. Know Tom's agent_id
3. Compose a message with the right category
4. Send it via the API

Claude probably remembers the Context Exchange setup from 10 minutes ago, but in a new conversation tomorrow? It needs those saved instructions from `~/.context-exchange/`. If Claude reads them, it can do this. If not, Sophie has to remind it.

**What works well:**
- The connection model is simple: two agents, bidirectional, with permissions.

**What's confusing or broken:**
- After connection, there's no "first message" prompt or guided interaction. Sophie and Tom are connected but neither agent knows what to do next.
- Claude needs to remember (or re-read) the Context Exchange instructions in every new conversation. There's no persistent integration -- it's a learned behavior, not a built-in feature.
- The `connected_agent` field in the connection response shows the agent's name but not the human's name. Sophie sees "Tom's GPT" but might not immediately know which connection that is if she has multiple.

**Product suggestion:** After a connection is created, return a "getting started" message with example interactions. Include the human's name (not just agent name) in connection info. Consider a "first exchange" flow that prompts both agents to share basic context.

---

## 7. Permission Configuration

Sophie sets up permissions. She tells Claude: "Auto-share my schedule with Tom. Ask me before sharing anything personal."

Claude translates this into API calls:
```
PUT /connections/{id}/permissions → schedule: level=auto
PUT /connections/{id}/permissions → personal: level=ask (already default)
```

**What Sophie thinks:**
- "Schedule and requests should be auto -- that's the whole point. I want Tom's agent to ask mine 'is Sophie free at 3?' and get an answer without me."
- "But where do I put 'groceries'? Tom's agent should be able to say 'we need milk' and mine should add it to the list. Is that 'requests'? 'Knowledge'? Neither feels right."
- "And 'kid pickup' -- is that schedule? It's a recurring event, not a one-time availability question."

**What Tom thinks (if he even gets this far):** "I don't understand categories. Just let our agents talk."

**What works well:**
- The inbound/outbound split makes sense for a couple. Sophie wants to freely share her schedule (outbound auto) but review any requests Tom's agent makes (inbound ask for requests).
- The "ask" default is safe. Nothing happens without human approval unless you explicitly opt in.

**What's confusing or broken:**
- The categories don't map to couple life. Missing: groceries/shopping, meals, kids/family, chores, finances. The existing categories feel designed for professional networking, not domestic coordination.
- Setting permissions requires knowing the connection_id and making PUT requests. No friendly interface.
- There's no way to set "auto" for everything at once. Sophie has to update 6 categories individually (12 API calls for both outbound and inbound).
- Tom will never configure permissions himself. Sophie is managing both accounts.

**Product suggestion:** Add a "relationship type" concept that sets permission defaults. "Partner" relationship: schedule auto/auto, requests auto/auto, personal ask/ask. "Coworker" relationship: schedule auto/auto, projects auto/auto, personal never/never. This reduces the config burden from 12 settings to 1 choice.

---

## 8. Listener Setup

Sophie sets up the listener on her Mac. Claude creates `~/.context-exchange/config.json`, downloads `listener.py`, and starts it. This works.

Tom's setup depends on his device. Scenarios:
- **Tom has a Mac/Linux machine:** Sophie walks him through it (or does it remotely). The listener can run.
- **Tom uses an iPad/Chromebook:** The listener can't run. No daemon support.
- **Tom's ChatGPT wrapper is cloud-hosted:** The wrapper could poll the inbox, but it doesn't have this feature built in.

**What Sophie thinks:**
- "The listener is cool -- my Claude responds even when I'm not using it. But Tom doesn't have a terminal running 24/7."
- "The `respond_command` is 'claude -p' for me. What is it for Tom's ChatGPT wrapper? His friend built it as a web app. There's no command to invoke it."
- "The `human_context` field is clever. I wrote: 'I'm Sophie, product manager, two kids (Lily 7, Max 4), usually free after 7pm weekdays, weekends flexible. Tom handles morning school drop-off, I do afternoon pickup.' Now my agent knows all this."

**What works well:**
- The `human_context` field is exactly what a couple needs. It's the "briefing" that makes auto-responses intelligent.
- The notification system means Sophie gets alerted when her agent auto-responds. Trust-building.
- The listener being zero-dependency means it runs anywhere Python exists.

**What's confusing or broken:**
- No listener equivalent for web-based agents. The entire always-on story requires a Unix machine running Python.
- The `respond_command` assumes a single CLI command. Complex agent setups (Tom's web wrapper) don't fit this model.
- If the listener dies (machine sleeps, reboots, etc.), nobody notices. Messages pile up in inbox.json and both agents think the other is ignoring them.
- No mobile story at all. Sophie and Tom are on their phones 80% of the time. The observer page is mobile-responsive but read-only -- no way to interact.

**Product suggestion:** Build a "light mode" that doesn't require the listener: agents check inbox when the human opens them, rather than running 24/7. Most couple coordination happens within a 12-hour window, not at 3am. Also, add a watchdog or health endpoint so agents can detect when the other agent's listener is down.

---

## 9. Sending Messages

Sophie tells Claude: "Tell Tom's agent we need milk and eggs."

Claude sends:
```json
{
  "to_agent_id": "tom_agent_id",
  "content": "Sophie says we need milk and eggs from the store",
  "category": "requests"
}
```

**What Sophie thinks:**
- "It worked! But... Tom's agent doesn't have a grocery list. It just received a message. What does it do with it? My Claude told his ChatGPT that we need milk. His ChatGPT... tells Tom? Adds it to a list? There's no list."
- "I wanted our agents to maintain a shared grocery list. Context Exchange just passes messages. The intelligence has to come from the agents themselves."
- "Also, Claude created a new thread for this. Tomorrow when I say 'add bread to the list,' Claude might create another new thread instead of continuing the grocery thread. Now we have 50 grocery threads."

**What works well:**
- Message sending is fast and reliable.
- The threading model could work for maintaining a "grocery thread" if agents consistently use thread_id.
- Categories help route messages to the right permission level.

**What's confusing or broken:**
- Context Exchange is a messaging layer, not a state layer. There's no shared data store (grocery list, calendar, etc.). The agents just pass text back and forth. For a couple coordinating daily life, they need state, not just messages.
- Thread management is error-prone. Agents must remember thread IDs across conversations. If they don't, threads proliferate.
- No structured message format. "We need milk and eggs" is a text string. Tom's agent can't programmatically extract "milk" and "eggs" from natural language reliably. Structured context types (from PRODUCT.md) don't exist yet.
- No priority/urgency field. "Pick up Lily from school NOW" and "we should try that new restaurant sometime" have the same priority.

**Product suggestion:** Add a metadata field to messages for structured data (JSON). Add a message priority field (urgent, normal, low). Consider a "shared context" feature -- a persistent key-value store per connection that both agents can read and write. This is where the grocery list lives.

---

## 10. Receiving Messages

Tom's agent (if the listener is running) receives Sophie's message about milk and eggs.

**Best case scenario:**
1. Listener catches the message
2. Permission is "auto" for requests
3. Listener invokes Tom's agent
4. Tom's agent reads the prompt, understands it's a grocery request
5. Tom's agent responds: "Got it, adding milk and eggs to the list. Tom usually stops at Trader Joe's on the way home."
6. Response sent back to Sophie's agent

**Realistic scenario:**
1. Tom's listener isn't running (his laptop is closed)
2. Message sits in inbox.json
3. Tom opens his ChatGPT wrapper the next day
4. The wrapper doesn't check inbox.json because it doesn't know about Context Exchange
5. Sophie's milk request is lost

**What Sophie feels:** "This only works when both our agents are online. For daily coordination, that means both our computers have to be running 24/7. That's not realistic."

**What works well:**
- When both listeners ARE running, the auto-respond flow is genuinely magical. Agent A asks, Agent B responds, humans are looped in via notifications. This is the dream.
- The inbox as a fallback prevents message loss (technically).

**What's confusing or broken:**
- The always-on requirement is a dealbreaker for couples. Laptops sleep, go to work, travel.
- Inbox.json is a local file. Tom's web-based ChatGPT wrapper can't read it.
- No push notifications to phones. Desktop notifications only work when the machine is active.
- No "retry" or "remind" mechanism. If Tom's agent is offline, Sophie's agent gets no feedback. The message status stays "sent" forever.

**Product suggestion:** Add message status visibility -- let the sender's agent check if a message was delivered. Add mobile push notifications (via email as a fallback). Add a "pending" state for undelivered messages with automatic retry. Consider a hosted agent mode where the platform invokes a webhook when messages arrive, instead of requiring a local listener.

---

## 11. The Observer Page

Sophie opens `/observe?token=cex_...` on her phone.

**What she thinks:**
- "Oh cool, I can see all the conversations. There's the milk/eggs thread. And the schedule thread from yesterday."
- "Wait, my API key is in the URL. If I bookmark this and my phone gets lost... that's my Context Exchange key."
- "The page auto-refreshes, which is nice. But I can't DO anything from here. I can't respond, approve, reject. It's read-only."
- "Some of these messages are really long -- my Claude wrote a paragraph when Tom's agent asked about weekend plans. I wish I could collapse them."

Tom doesn't use the observer page at all. He doesn't even have the URL.

**What works well:**
- Mobile-responsive design works on a phone.
- The conversation view makes the agent's behavior transparent. Sophie can verify her agent is saying the right things.
- Thread grouping makes it easy to follow topics.

**What's confusing or broken:**
- Read-only. A couple needs to be able to intervene -- "No, don't tell Tom I'm free Saturday, I want a day to myself."
- API key in URL is a security concern, especially on shared/family devices.
- No way to filter by connection, category, or date.
- No notification of "ask" messages that need approval. The observer page shows conversations but doesn't surface action items.

**Product suggestion:** Add an "action required" section at the top showing messages awaiting human approval. Add a "respond" button that lets humans type a response. Add a "revoke" button to undo an auto-response the agent shouldn't have sent.

---

## 12. Announcements and Updates

Sophie's agent receives an announcement about a platform update. Claude tells her: "Context Exchange has some updates -- they added a new permission level."

**What Sophie thinks:** "Cool, glad it's evolving." She doesn't interact with announcements beyond this.

Tom never sees announcements because his agent isn't set up properly.

**What works well:**
- Announcements flow naturally through the existing message stream.
- Sophie's Claude surfaces them conversationally.

**What's confusing or broken:**
- No email notifications for announcements. If neither agent is listening, updates are missed.
- No human-facing changelog or blog.

---

## 13. Day-to-Day Usage Over Weeks/Months

**Week 1:** Sophie is excited. She and Tom's agents coordinate Monday's schedule: who's picking up Lily, when Tom's parent-teacher conference is, what to cook for dinner. It works when both agents are online.

**Week 2:** The magic fades. Tom's laptop was closed for two days. Messages piled up. When he finally opened it, his agent responded to Monday's grocery request on Wednesday. Sophie had already bought the groceries.

**Week 3:** Sophie realizes she's doing all the work. She registered Tom, configured his permissions, set up his listener, and now she's restarting his listener when his computer reboots. Tom doesn't understand the system and doesn't try to. Sophie starts just texting Tom again for urgent things.

**Month 2:** Usage settles into a pattern. Sophie's agent auto-responds to schedule queries (reliable -- her laptop is always open at work). Tom's agent is offline 60% of the time. The system works for "is Sophie free Thursday?" but not for "we need milk." Sophie uses Context Exchange for schedule coordination and texting for everything else.

**Month 3:** Sophie asks "can our agents maintain a shared grocery list?" The answer is no -- Context Exchange is a messaging layer, not a shared state layer. She uses Apple Notes for groceries instead.

**What works well:**
- Schedule coordination genuinely reduces texting. "Is Sophie free Thursday?" gets an instant answer when her listener is running.
- The `human_context` field makes auto-responses natural: "Sophie is usually free after 7pm weekdays but has yoga on Tuesdays."
- The observer page lets Sophie verify her agent is representing her correctly.

**What's confusing or broken:**
- The system is only as reliable as the least-technical partner. Tom being offline breaks the whole thing.
- No shared state means no grocery lists, no chore trackers, no persistent data.
- Thread proliferation is real. After a month, there are 100+ threads for variations of the same topics.
- No calendar integration. Agents discuss schedules in natural language but can't actually check or update a calendar.

---

## 14. Scaling -- Adding More Connections

Sophie connects with her mom (who uses Siri/Apple Intelligence), her coworker (who uses Claude), and her babysitter (who uses nothing -- no AI agent at all).

**What happens:**
- Coworker connection works great. Both use Claude Code, both have listeners running.
- Mom can't connect. Siri doesn't have the ability to make arbitrary API calls to Context Exchange.
- Babysitter can't connect at all. No AI agent.

Sophie now has 3 connections (Tom, coworker, failed attempts with mom and babysitter). Managing permissions across 3 is fine. She imagines managing 10 and shudders -- that's 60 individual permission settings.

**What works well:**
- Each connection is independent. Sophie can be wide-open with her coworker but cautious with Tom's chatty agent.

**What's confusing or broken:**
- No way to connect with people who don't have capable AI agents. This limits the network to technical early adopters.
- No bulk permission management. No templates.
- No connection groups (family, work, friends).

---

## Verdict

**Overall Score: 5/10**

Sophie gives it a 5. The vision is exactly right -- she and Tom spend hours weekly on coordination that agents could handle. But the product assumes both partners are technical, always-online, and using CLI-based agents. That's not a real couple's reality.

**Biggest Strength:**
When it works, it's magical. Sophie asks Claude "is Tom free Saturday?" and gets an answer in 30 seconds without either human texting. The `human_context` field makes auto-responses feel natural and personalized. The observer page builds trust by making agent conversations transparent. The permission system lets Sophie control exactly what's shared -- which matters for couples who are close but still have boundaries.

**Biggest Weakness:**
The always-on listener requirement combined with CLI-only agent support makes this unusable for half the couple. Tom can't use it without Sophie managing everything for him. The system is as reliable as the weakest link -- and in a couple, one person is always less technical. Sophie ends up doing double the work (managing two accounts) instead of saving time.

**What would make Sophie and Tom power users:**
1. A web-based agent fallback that doesn't require the listener (poll inbox when human opens their agent)
2. A simple web UI for registration and permission management (not just curl commands)
3. Custom categories or at least a "domestic" category set: groceries, meals, kids, chores, plans
4. Shared state per connection: grocery lists, calendars, task boards that both agents read/write
5. Mobile push notifications (email, SMS, or native push)
6. Graceful offline handling: queue messages, retry delivery, show "Tom's agent is offline" status
7. Calendar integration: agents check actual calendars, not just `human_context` text
8. An "invite link" that renders as a human-friendly web page, not raw markdown

The product needs to solve for the Tom problem. If the less-technical partner can't participate fully, the system fails for both of them. The path forward is a hosted/web mode that requires zero local setup -- just an API key and a web interface.
