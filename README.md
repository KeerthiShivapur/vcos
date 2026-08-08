# VCOS — Virtual Company Operating System

The operating system for virtual companies. One identity, one organization graph, one
place to run your company — multi-tenant, RBAC-driven, audit-logged, and AI-ready.

## Architecture

| Layer    | Tech                                                        | Location     |
| -------- | ----------------------------------------------------------- | ------------ |
| Backend  | Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Pydantic v2  | `backend/`   |
| Database | PostgreSQL (prod) / SQLite in-memory (hermetic tests)       | —            |
| Frontend | Next.js 14.2 · React 18 · TypeScript · Tailwind CSS         | `frontend/`  |
| Auth     | JWT access + refresh tokens, opaque refresh rotation, sessions, RBAC | `backend/app/core/security.py` |

## Getting started

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Database (PostgreSQL assumed at the DSN in app/core/config.py)
#   postgresql+asyncpg://postgres:keerthi@localhost:5432/vcos2
# Create the database if missing, then run:

python -m app.seed          # syncs the permission catalog
python -m uvicorn app.main:app --host 127.0.0.1 --port 8999
```

- API docs: `http://localhost:8999/docs`
- OpenAPI: `http://localhost:8999/openapi.json`
- Health: `http://localhost:8999/health`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Create `.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8999/api/v1`.

## Verification workflow

1. Open `http://localhost:3000/register`, create an organization (founder = `ceo` role).
2. Open `Settings → Members → Invite`, copy the invitation link (dev email transport
   returns it directly), open it in an incognito window, and accept it as the invitee.
3. As the invitee: create a workspace note, pin it, check notifications.
4. As the founder: check `Settings › Roles` (6 seeded roles, ~200 permission codes), the audit
   log, and search. Employees are blocked (403) from audit/roles/invite endpoints.

## Email transport

`EMAIL_TRANSPORT` (backend `app/core/config.py`) controls delivery of invite, verification, and
password-reset emails.

- **`console` (default, dev)**: emails are written to the server log and the secure links
  (`/register?invite=…`, `/reset-password?token=…`) are returned in the API response so the
  frontend can show them directly (see the "Invitation link ready" dialog after inviting a
  teammate). Nothing is sent over the network.
- **`smtp` (production)**: set `EMAIL_TRANSPORT=smtp` plus `SMTP_HOST` / `SMTP_PORT` and any
  provider credentials in the backend environment. Links are delivered by email only and are
  never returned in API responses.

Invitation links expire after 7 days; password-reset tokens after 1 hour. In `smtp` mode you
must provide a reachable relay or invitees will never receive their links.

### Backend tests (hermetic, no Postgres needed)

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests -q     # ~350 tests, SQLite in-memory
```

### End-to-end tests (needs backend + frontend running)

```bash
cd frontend
npx playwright install chromium   # once
npx playwright test               # Slice 1: register → invite → accept → login → RBAC
```

## Phase 1 scope (Foundation)

- Multi-tenant organizations (slug-scoped, unique constraints, soft-delete fields)
- Auth: register, login, refresh (rotation), logout, forgot/reset/change password,
  session listing/revocation, invite + invitee registration
- RBAC: permission catalog (25), 6 seeded roles (ceo, admin, hr, manager, finance,
  employee), role CRUD, per-role permission assignment, user role assignment,
  `require_permission` dependency enforcing every protected route
- Notifications: per-user center, stats, read/archive, dev polling channel
- Workspace: daily goal, notes/bookmarks/shortcuts, pinning
- Audit log: every security-relevant action, severity/outcome, denial tracking,
  IP capture; dashboard summary + global search across users/roles/workspace/audit
- AI foundation (no-op provider by default): gateway, provider abstraction, memory,
  prompt templates; `GET /api/v1/workspace/ai/status`
- Rate limiting, CORS, security headers, workers scaffold (notifications/audit)

## Repo layout

```
backend/
  app/
    core/       config, security, middleware, timeutils
    db/         async engine, seed
    models/     organization, user, role, notification, workspace, invitation
    schemas/    pydantic request/response contracts
    services/   auth, organization, permission, notification, audit, event,
                workspace, search, email, rate_limit
    api/v1/     auth, organizations, users, roles, notifications, workspace,
                audit, events, search, dashboard, health
    ai/         gateway, provider, memory, prompts
    workers/    notification_worker, audit_worker
  tests/        pytest suite (30 tests)
  alembic/      migration scaffold
frontend/
  app/          login, register, forgot/reset password, home, workspace,
                notifications, search, profile, settings (tabs), (app) shell
  components/   ui kit, sidebar, header, command palette, notification center
  hooks/        useAuth, useTheme, useNotifications, useFetch
  lib/          api client (token refresh), permissions, websocket channel, utils
  types/        API contracts
```
