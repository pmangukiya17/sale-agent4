# Sales Agent — M0: Foundations

This milestone contains no discovery, verification, scoring, personalization, or
Outlook logic. It is the production-grade skeleton everything else will be
built on: project structure, FastAPI backend, Postgres + Alembic migrations,
JWT authentication, the CRM schema, a Dockerized dev environment, and a
dashboard shell (login + protected layout + empty Pipeline/Contacts/Settings
pages) wired to real API calls.

## What's included

- `backend/` — FastAPI app, SQLAlchemy models for the full CRM schema
  (Users, Companies, Contacts, WebsiteFindings, ICPCriteria, Threads,
  Messages, FollowUps, AuditLogs), JWT auth, Alembic migrations.
- `frontend/` — React + Vite + TypeScript + Tailwind dashboard shell:
  login page, auth context, protected routes, sidebar layout, and a
  Companies list page (Pipeline) that calls the real API.
- `docker-compose.yml` — Postgres, backend, frontend, wired together.
- `backend/entrypoint.sh` + `backend/app/wait_for_db.py` — the backend
  container waits for Postgres to be genuinely reachable (retrying with
  backoff) before running migrations and starting the app, instead of
  relying solely on `depends_on`'s healthcheck gate, which only guarantees
  the db *container* passed its healthcheck at some point, not that the
  "db" hostname/connection is already usable at the exact instant the
  backend container starts.

## Prerequisites

- Docker and Docker Compose installed locally.
- Nothing else — Python and Node both run inside containers.

## Running it locally

1. Copy the environment template and edit `SECRET_KEY` (and the admin
   password) before doing anything real with it:

   ```bash
   cp .env.example .env
   ```

2. Start everything:

   ```bash
   docker compose up --build
   ```

   This will:
   - Start Postgres and wait for it to be healthy.
   - Run `alembic upgrade head` against it to create the CRM schema.
   - Start the FastAPI backend on `http://localhost:8000`, which
     auto-creates one admin user on first boot using
     `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` from `.env`.
   - Start the Vite dev server on `http://localhost:5173`.

3. Open `http://localhost:5173` and log in with the admin credentials
   from your `.env` file. You'll land on the (empty) Pipeline page —
   that emptiness is expected, since Discovery is M1, not M0.

4. API docs (Swagger UI) are available at `http://localhost:8000/docs`
   for manually exercising `/companies` while there's no discovery
   engine feeding it yet.

## Useful commands

```bash
make up             # docker compose up --build
make down            # stop everything
make logs             # tail all container logs
make migrate           # re-run alembic upgrade head manually
make revision m="msg"    # generate a new alembic migration
make backend-shell        # shell into the backend container
make db-shell               # psql into the database
make smoke-test               # run the automated smoke test (see below)
```

## Smoke test — mandatory before every milestone

`smoke_test.py` (stdlib-only, no dependencies to install) checks the 17
things every milestone is gated on, against an already-running stack:

M0:
1. Backend starts (`/api/v1/health`)
2. Frontend starts
3. `/docs` responds
4. Login succeeds (using `FIRST_ADMIN_EMAIL`/`FIRST_ADMIN_PASSWORD` from `.env`)
5. Company creation succeeds
6. Contact creation succeeds

M1.1 (Company Profile & Discovery Configuration):
7. Workspace Settings reachable (auto-bootstraps on first call)
8. Company Profile creation succeeds
9. Default Company Profile enforcement (marking a second profile as default unsets the first)
10. Product creation succeeds
11. ICP Criteria creation succeeds
12. Knowledge Base entry creation succeeds

M1 (Buyer Discovery Engine):
13. Search Templates reachable (system-seeded defaults from migration 0003)
14. Discovery Search creation succeeds (pinned to the ICP from step 11)
15. Discovery Search run succeeds (manual_csv provider, synchronous, creates a prospect)
16. Prospects list succeeds (the run's prospect is visible)
17. Prospect approve succeeds

Run it after `docker compose up --build` is up:

```bash
python3 smoke_test.py
# or
make smoke-test
```

It prints PASS/FAIL per step and exits `0` only if all 17 pass. No new
milestone work starts until this exits `0` on a clean `down -v && up --build`.

## What to verify once it's running

- `GET http://localhost:8000/api/v1/health` returns `{"status": "ok"}`.
- Logging in via the dashboard works with the bootstrapped admin user.
- Creating a company via `POST /api/v1/companies` (through `/docs`) makes
  it show up on the Pipeline page after a refresh.
- Creating a contact via `POST /api/v1/contacts` (through `/docs`, with the
  `company_id` from a company you already created) makes it show up on the
  Contacts page after a refresh.
- Restarting the containers doesn't wipe data (Postgres uses a named
  volume) and doesn't re-create a duplicate admin user.

**If login with `.env` credentials ever fails on a database that isn't
brand new:** the admin bootstrap only runs once — the first time the
`users` table is empty. If you change `FIRST_ADMIN_PASSWORD` in `.env`
after that has already happened, the existing user's stored password
doesn't change to match. Check the backend logs for a
`"Skipping admin bootstrap — N user(s) already exist"` line, which means
this is what happened. The fix is `docker compose down -v` (wipes the
volume so bootstrap runs fresh against the current `.env`), not editing
this code.

## Known limitations (intentional — out of scope for M0)

- No discovery, verification, website analysis, scoring, personalization,
  Outlook, or follow-up logic. Companies can only be created manually via
  the API right now.
- Single admin-style auth model — no team roles/permissions beyond
  `admin` / `operator`, no password reset flow yet.
- No unit/integration test suite yet — only the `smoke_test.py` end-to-end
  gate described above. A real test suite starts landing alongside actual
  business logic from M1 onward.

## Repo layout

```
sales-agent/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app, CORS, router wiring, admin bootstrap
│   │   ├── core/               settings (config.py), password hashing + JWT (security.py)
│   │   ├── db/                 SQLAlchemy engine/session, declarative base
│   │   ├── models/              CRM schema (one file per table)
│   │   ├── schemas/            Pydantic request/response models
│   │   ├── api/routes/          health, auth, companies, contacts
│   │   └── wait_for_db.py      retries DB connectivity before migrations run
│   ├── alembic/                migrations (0001 = initial CRM schema)
│   ├── entrypoint.sh           wait-for-db -> alembic upgrade -> exec uvicorn
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── api/client.ts        axios instance, JWT attach/refresh-on-401
│       ├── auth/AuthContext.tsx  login/logout/current-user state
│       ├── components/           Sidebar, ProtectedRoute
│       ├── layouts/              DashboardLayout
│       └── pages/                Login, Pipeline, Contacts, Settings
├── docker-compose.yml
├── Makefile
├── smoke_test.py         mandatory PASS/FAIL gate before every milestone
└── .env.example
```
