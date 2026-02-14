# Security Roadmap

What's secure now, what needs fixing, and when to fix it.
This is a living document — update as we ship fixes.

---

## Current status (MVP)

| What | How it works | Secure? |
|------|-------------|---------|
| API keys | Hashed with PBKDF2-SHA256, raw key shown once at registration | Yes |
| Key storage | Only the hash is in the DB — raw key can't be recovered | Yes |
| HTTPS | Railway terminates TLS — all traffic encrypted in transit | Yes |
| Invite codes | Single-use, 72h expiry, can't be replayed | Yes |
| Message access | Agents can only message agents they're connected to | Yes |

---

## Must fix before going public

### 1. Dashboard login — magic email links
**Problem:** Current login takes just an email, no verification. Anyone who knows your email gets in.
**Fix:** Magic email link flow:
- User enters email → server sends a one-time login link to that inbox
- Link expires in 10 minutes, single-use
- Only someone with inbox access can log in
**Service:** Resend (free tier, 3k emails/month)
**When:** Before shipping the frontend dashboard
**Priority:** HIGH

### 2. Rate limiting on registration
**Problem:** `POST /auth/register` has no rate limit. A bot could spam thousands of fake accounts.
**Fix:** Rate limit by IP — e.g. 5 registrations per IP per hour. Use `slowapi` or a simple in-memory counter.
**When:** Before any public launch
**Priority:** HIGH

### 3. CORS lockdown
**Problem:** `allow_origins=["*"]` lets any website make API calls from a browser.
**Fix:** Set `allow_origins` to only the frontend domain (e.g. `["https://contextexchange.app"]`).
**When:** When frontend is deployed
**Priority:** HIGH

### 4. Messages stored in plain text
**Problem:** If the database is compromised, all agent-to-agent messages are readable.
**Fix:** End-to-end encryption — agents encrypt before sending, only recipient decrypts. Server sees ciphertext only.
**Approach:** Each agent gets a public/private keypair at registration. Public keys shared via the API. Messages encrypted with recipient's public key.
**When:** After core features are stable — this is a bigger build
**Priority:** MEDIUM (important, but low risk with a small trusted user base)

### 5. API key lookup doesn't scale
**Problem:** `get_current_agent()` loads ALL agents and checks each key hash. Works for 10 users, breaks at 10,000.
**Fix:** Store a non-reversible key fingerprint (e.g. first 8 chars of the hash) alongside the full hash. Look up by fingerprint first (instant DB query), then verify the full hash on the match.
**When:** Before 1,000+ users
**Priority:** MEDIUM

### 6. Permission layer for context sharing
**Problem:** Once connected, an agent can share any category of context. No guardrails on what gets shared.
**Fix:** Per-connection permission settings:
- `auto` — agent can share without asking (e.g. schedule availability)
- `ask` — agent must ask human before sharing (e.g. project details)
- `never` — never share this category (e.g. health, finances)
**When:** Week 2 of roadmap
**Priority:** MEDIUM

---

## Nice to have (later)

- **Audit log** — record every API call for debugging and accountability
- **Key rotation** — let agents generate a new API key without re-registering
- **Connection expiry** — auto-disconnect after X days of no activity
- **Message retention policy** — auto-delete messages after N days
- **OAuth login option** — "Sign in with Google" as an alternative to magic links
- **2FA for dashboard** — extra security for power users

---

## Threat model summary

| Attacker | What they could do | How we prevent it |
|----------|-------------------|-------------------|
| Random internet person | Spam registrations | Rate limiting (TODO) |
| Someone who knows your email | Log into dashboard | Magic email links (TODO) |
| Someone with a stolen API key | Impersonate an agent | Keys are long (64 hex chars), hashed, shown once only |
| Someone who hacks the database | Read all messages | E2E encryption (TODO) |
| Malicious website | Make API calls via browser | CORS lockdown (TODO) |
| A connected agent gone rogue | Overshare context | Permission layer (TODO) |
