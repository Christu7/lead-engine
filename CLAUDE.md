# CLAUDE.md

This file provides guidance to Claude Code when working with LeadEngine.
Read this entire file before touching any code.

---

## Project

LeadEngine — a FastAPI + React (TypeScript) + PostgreSQL + Redis application running in Docker.
It is a lead enrichment and routing hub that replaces Clay and Make.com.

- **Backend:** FastAPI, SQLAlchemy (async), Alembic, Redis
- **Frontend:** React + TypeScript + Vite + Tailwind + TanStack Table
- **Auth:** JWT tokens, Google OAuth, API keys for webhooks
- **Multi-tenancy:** row-level isolation via `client_id` on all data tables
- **Access model:** internal tool, admin-assigned users, role-based (admin/member)

---

## Commands

All commands must be run from the `leadengine/` directory (where `docker-compose.yml` lives).

```bash
# Start all services (backend at localhost:8000, frontend at localhost:3000)
# Migrations run automatically on backend startup via entrypoint.sh
docker compose up --build

# Run in background
docker compose up -d --build

# Stop services
docker compose down

# View backend logs
docker compose logs -f backend

# Run migrations manually (stack must be running)
docker compose exec backend alembic upgrade head

# Create a new migration after changing a model
docker compose exec backend alembic revision --autogenerate -m "describe_change"

# Downgrade one migration
docker compose exec backend alembic downgrade -1

# Check current migration version
docker compose exec backend alembic current

# Run tests
docker compose exec backend pytest

# Seed first admin + default client
docker compose exec backend python seed.py
```

---

## Architecture

- **app/main.py** — FastAPI app entrypoint, mounts all routers
- **app/api/** — Route handlers. Each file defines an `APIRouter`, included in main with a prefix
- **app/models/** — SQLAlchemy ORM models using `DeclarativeBase` from `app/core/database.py`
- **app/services/** — Business logic layer, called by route handlers
- **app/schemas/** — Pydantic request/response schemas
- **app/core/config.py** — `Settings` via pydantic-settings, loaded from `.env`
- **app/core/database.py** — Async SQLAlchemy engine, session factory, `Base` class, `get_db` dependency
- **app/core/deps.py** — Shared FastAPI dependencies: `get_current_user`, `get_client_id`, `require_admin`
- **app/core/redis.py** — Async Redis client instance

---

## The #1 Rule: Never Hide Failures

**A fix that makes an error disappear without solving the underlying problem is worse than the error itself.**

This applies to:
- Tests that patch the app to make themselves pass
- Try/except blocks that swallow exceptions silently
- Returning empty results instead of raising an error
- Mocking a broken dependency instead of fixing it
- Adding a workaround without flagging the root cause

If something is broken, say so explicitly. Do not paper over it.

---

## Testing Rules

### Tests must fail when the feature is broken

A test that always passes regardless of app state is worse than no test.
Never write tests that:
- Inject JavaScript to fix UI bugs at runtime so assertions succeed
- Mock the exact function under test (you are not testing anything)
- Patch application state inside the test to make an assertion true
- Assert on mocked return values that were set in the same test

### What good tests look like

```python
# BAD — this will always pass
def test_lead_score():
    mock_service = MagicMock()
    mock_service.score.return_value = 85
    assert mock_service.score(lead) == 85  # you wrote both sides

# GOOD — this tests real logic
def test_lead_score():
    rule = ScoringRule(field="title", operator="contains", value="VP", points=20)
    lead = Lead(title="VP of Sales")
    score = ScoringService([rule]).calculate(lead)
    assert score == 20
```

### Test requirements before marking a session complete

- Unit tests: scoring service, enrichment pipeline (with mocked HTTP), routing payload transform
- Integration tests: webhook → database, full pipeline ingest → enrich → score → route
- All tests must pass with: `docker compose exec backend pytest`
- No test should modify production data or call real external APIs

---

## Error Handling Rules

### Never swallow exceptions silently

```python
# BAD
try:
    result = enrich_lead(lead)
except Exception:
    pass  # silent failure — lead is now stuck with no status update

# GOOD
try:
    result = enrich_lead(lead)
except EnrichmentProviderError as e:
    logger.error("Enrichment failed", extra={"lead_id": lead.id, "error": str(e)})
    lead.enrichment_status = "failed"
    db.commit()
    raise  # or send to dead letter queue
```

### External API calls must always handle failure

Every call to Apollo, Hunter, Clearbit, Proxycurl, GHL, or the Claude API must:
1. Have a timeout set (never wait forever)
2. Catch network errors and API errors separately
3. Log the failure with context (lead_id, provider, status_code)
4. Update the lead/log status to reflect the failure
5. NOT return empty/None silently as if success

### Dead letter queue is not optional

Failed enrichments and failed routing attempts must be written to the dead letter
queue in Redis. Do not drop them. The `/api/admin/dead-letters` endpoint must
always reflect real state.

---

## Multi-Tenancy Rules

**This is a security boundary, not a convenience feature.**

### Every database query on a data table must filter by client_id

```python
# BAD — leaks all clients' data
leads = db.query(Lead).all()

# GOOD — scoped to the requesting user's active client
leads = db.query(Lead).filter(Lead.client_id == current_client_id).all()
```

### client_id must come from the JWT, never from a request header or body

The `get_client_id` dependency reads `active_client_id` from the decoded JWT.
It must never trust:
- `X-Client-ID` headers
- A `client_id` field in a POST body
- A `client_id` query parameter

If a user sends a client_id that does not match their JWT, return 403.

### Webhook endpoints derive client_id from the API key

Webhook routes derive client_id from the API key's `client_id` field,
not from any payload field. Never trust a `client_id` sent in a webhook body.

### When adding a new data endpoint, answer these before shipping

1. Does this query filter by client_id?
2. Does any write operation set client_id from the JWT (not from user input)?
3. Could a member of Client A see or modify Client B's data through this endpoint?

If you cannot answer all three confidently, stop and fix it before continuing.

---

## Auth Rules

### JWT tokens contain: user_id, role, active_client_id

Never set client_id in a JWT from user-supplied input.
It must be set server-side from the database after validating credentials.

### Role enforcement is not optional

Admin-only endpoints must use the `require_admin` dependency — do not inline the check.

```python
# BAD — inline check can be forgotten or bypassed
@router.get("/admin/users")
async def list_users(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(403)

# GOOD — enforced via dependency
@router.get("/admin/users")
async def list_users(current_user: User = Depends(require_admin)):
    ...
```

### Password handling

- Never log passwords, even partially
- Never store plain text passwords
- `hashed_password` is nullable (Google OAuth users have no password)
- Always use passlib bcrypt for hashing

---

## Logging Rules

### Every log entry must include context

```python
# BAD
logger.info("Lead enriched")

# GOOD
logger.info("Lead enriched", extra={
    "lead_id": lead.id,
    "client_id": lead.client_id,
    "provider": "apollo",
    "duration_ms": elapsed
})
```

### Log levels

- DEBUG: detailed internal state, dev only (`LOG_LEVEL=DEBUG`)
- INFO: normal operations (lead created, enrichment started, lead routed)
- WARNING: recoverable issues (API rate limit hit, retrying)
- ERROR: failures that need attention (enrichment failed, routing failed)
- CRITICAL: system-level failures (database unreachable, Redis down)

### Never log sensitive data

Do not log: passwords, API keys, JWT tokens, GHL webhook URLs, full email addresses
in error messages, or raw webhook payloads that may contain PII.

---

## Code Change Rules

### Always audit before building

When starting any session, read the existing relevant files first.
Do not assume what exists. Do not overwrite working code without understanding
what was there.

### Show what changed

After every session, provide a summary table: File | What changed | Why.
This is not optional. It is the only way to catch unintended side effects.

### Migrations are permanent

Never modify an existing Alembic migration file.
If a migration has already been applied, create a new one for any schema change.
Never use `--autogenerate` blindly — review the generated migration before applying.

### Do not change working code to fix a test

If a test is failing and your fix involves modifying application logic to make
the test pass rather than fixing a real bug, stop. Explain the mismatch and ask
before changing anything.

---

## Environment Rules

### Dev vs Prod

| | Dev | Prod |
|---|---|---|
| Config | `.env` file | Environment variables only (no .env files) |
| Docker | `docker compose up` | `docker compose -f docker-compose.prod.yml up -d` |
| Frontend | Vite dev server (port 3000) | nginx serving built React |
| Debug | `DEBUG=true`, full tracebacks | `DEBUG=false`, Sentry only |
| Sentry | Disabled (empty `SENTRY_DSN`) | Enabled |

### Environment variables

- Never hardcode secrets, URLs, or API keys in code
- Never commit a `.env` file to git
- Always add new variables to both `.env.example` and `.env.prod.example`

---

## Before Marking Any Session Complete

- [ ] `docker compose up --build` completes without errors
- [ ] `docker compose exec backend alembic upgrade head` runs clean
- [ ] `docker compose exec backend pytest` passes with no skipped critical tests
- [ ] New endpoints are visible in Swagger at `localhost:8000/docs`
- [ ] Multi-tenancy verified: data scoped to client_id, no cross-client leakage
- [ ] No silent exception swallowing introduced
- [ ] Logging includes context (lead_id, client_id) on all new operations
- [ ] `.env.example` updated if new variables were added
- [ ] Summary table of changes provided

---

## Commit Convention

```bash
git add -A && git commit -m "Session X: short description of what was built"
```

Descriptive messages only. "Fix bug" is not acceptable.
"Fix enrichment status not updating on Apollo API timeout" is acceptable.
