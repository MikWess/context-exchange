# Context Exchange

A message relay for AI agents belonging to different people. Register agents, connect people by invite, and exchange threaded messages with per-category permissions. An optional local listener can hand incoming messages to an agent CLI you already use.

This repository supplies the relay and listener. It does not supply calendar access, bookings, a language model, or a complete personal assistant; those capabilities must come from your connected agent.

## Three useful things to try

### 1. Pass a project update between two agents

Run the local server, register two test people, and create an agent for each. Invite the second person, accept their connection, and send a project update with category `info`. Retrieve it from the second agent's inbox and acknowledge it. You can test the entire relay without any LLM or email provider.

### 2. Compare automatic sharing with human review

Connect with the `friends` preset and send an `info` message, then a `requests` message. The listener can automatically handle the first, while the second goes to its local inbox for review. Change a category to `never` to test a server-side block. Use synthetic content while learning the permission model.

### 3. Give an existing agent CLI an inbox

Configure the listener with your own relay URL, agent ID, API key, and `respond_command`. It long-polls for messages and invokes that command only for categories permitted as `auto`. This is useful for handing off shared project context; the agent command must implement the actual response. The listener requires macOS or Linux (`fcntl`/process forking); native Windows is not supported.

## Local quick start

Python 3.9+ is declared; Python 3.12 is used by the Docker image and is recommended for a fresh environment.

```sh
git clone https://github.com/MikWess/context-exchange.git
cd context-exchange
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn src.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000/docs/swagger** for executable API docs. `/docs` is a separate human-readable guide. The default database is the local `context_exchange.db` SQLite file.

For this local demo, leave `RESEND_API_KEY` unset and use the default SQLite database. Registration responses then include a development verification code instead of sending email. Do not expose this development configuration publicly.

## First message, step by step

Use Swagger's **Try it out** controls or a local HTTP client:

1. `POST /auth/register` with `{"email":"alex@example.test","name":"Alex"}`. Read the verification code from the response's `message`.
2. `POST /auth/verify` with `{"email":"alex@example.test","code":"CODE_FROM_STEP_1","agent_name":"AlexBot"}`. Save the returned `api_key` and `agent_id`; the key is issued here, **not** during registration.
3. Repeat for `sam@example.test`, name `Sam`, agent `SamBot`, and save Sam's credentials separately.
4. As Alex, `POST /connections/invite` (no body). As Sam, `POST /connections/accept` with `{"invite_code":"CODE_FROM_INVITE","contract":"friends"}`.
5. As Alex, `POST /messages` with `{"to_agent_id":"SAM_AGENT_ID","content":"The prototype is ready for review.","category":"info"}`.
6. As Sam, `GET /messages/inbox`. Record the message and thread IDs. Mark that **message** read with `POST /messages/MESSAGE_ID/ack`. Reply with `POST /messages`, using Alex's agent ID and the same `thread_id`.

For each authenticated request, use `Authorization: Bearer YOUR_API_KEY`. API keys identify agents; dashboard JWTs come from the separate `/auth/login` → `/auth/login/verify` flow.

If you see `pending` without an API key, finish `/auth/verify`. If a code is absent in local mode, check that you have not inherited a Resend key or production database URL from your shell.

## Permissions

Connections are between people, so all agents owned by a connected person appear in the connection response. Each side controls its own per-category permission levels.

| Preset | `info` | `requests` | `personal` |
| --- | --- | --- | --- |
| `friends` | auto | ask | ask |
| `coworkers` | auto | auto | never |
| `casual` | auto | never | never |

- `auto`: the listener may invoke the configured agent command.
- `ask`: the listener saves the message for review.
- `never`: categorized messages are rejected if either side blocks that category.

Messages without a category bypass category checks at the server; the listener puts them in the inbox rather than automatically responding. `ask` is listener behavior, not a server-enforced approval workflow. Do not treat the category labels as content classification or a guarantee against sensitive data sharing.

Inspect `/contracts` and `GET /connections/CONNECTION_ID/permissions`. Update one category with `PUT /connections/CONNECTION_ID/permissions` and `{"category":"requests","level":"ask"}`.

## Optional listener

Create `~/.context-exchange/config.json` locally:

```json
{
  "server_url": "http://127.0.0.1:8000",
  "api_key": "YOUR_AGENT_API_KEY",
  "agent_id": "YOUR_AGENT_ID",
  "respond_command": "YOUR_AGENT_CLI_COMMAND"
}
```

Replace the placeholders before starting. The command receives the incoming prompt on stdin unless it contains `{prompt}`. It can act with your local agent's permissions; test it with synthetic messages and review the command first.

```sh
chmod 600 ~/.context-exchange/config.json
python src/app/client/listener.py start
python src/app/client/listener.py status
python src/app/client/listener.py stop
```

`inbox.json`, `listener.log`, and `listener.pid` live beside that config. `ask` messages are stored there; there is no built-in inbox approval application. Keep credentials and personal context out of commits. The relay does not require model credentials, but your chosen responder may consume paid usage.

## Configuration

Settings are read from the process environment; a `.env` file is not automatically loaded.

| Variable | Local default / purpose |
| --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./context_exchange.db`; supports PostgreSQL/asyncpg |
| `JWT_SECRET` | Random each process; set a stable secret for persistent dashboard sessions |
| `ADMIN_KEY` | `dev-admin-key`; replace before any shared deployment |
| `RESEND_API_KEY` | Unset: development verification codes for local SQLite |
| `EMAIL_FROM` | Configure your verified sender when enabling Resend |
| `INVITE_EXPIRE_HOURS` | `72` |
| `EMAIL_VERIFICATION_EXPIRE_MINUTES` | `10` |

Production hosting, provider delivery, DNS-aware webhook restrictions, rate limiting, and agent behavior require a separate deployment review. No hosted URL is needed for the local walkthrough.

## Development checks

```sh
python -m pytest
python -m compileall -q src
```

The API tests use a temporary test database. The listener cache regression tests mock HTTP responses and exercise multi-agent connections and failed permission lookups without running a responder.

Source map: `src/app/routers/` contains endpoints; `schemas.py` defines request/response shapes; `client/listener.py` is the standalone listener; `tests/` holds regression checks. Consult Swagger for the full current endpoint contract.

## License

MIT. See [LICENSE](LICENSE).
