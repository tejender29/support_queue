# Support Queue

Support Queue is a small helpdesk application for managing IT support tickets. The FastAPI backend stores tickets and agents in SQLite, calculates response due dates from priority, and exposes an active queue ordered by SLA urgency. A React dashboard provides the day-to-day queue view on top of that API.

## Technology stack

### Backend

- Python
- FastAPI
- Uvicorn
- SQLite
- SQLAlchemy 2
- Pydantic 2
- Pytest

### Frontend

- React
- TypeScript
- Vite
- Plain CSS

## Project structure

```text
app/
  db.py          SQLite engine, SQLAlchemy base, and session dependency
  main.py        FastAPI application and CORS configuration
  models.py      Ticket, Agent, enums, and UTC datetime type
  routes.py      Ticket, agent, assignment, and queue endpoints
  schemas.py     Pydantic request and response models
  services.py    SLA, UTC, overdue, and queue ordering logic
frontend/
  src/           React dashboard, API client, and styles
  index.html     Dashboard entry document
  package.json   Frontend scripts and dependencies
  vite.config.ts Development proxy configuration
tests/
  test_api.py    API integration tests
  test_queue.py  Queue and SLA unit tests
README.md
REASONING.md
AI_LOGS.md
requirements.txt
pytest.ini
```

## Backend setup

From a fresh clone:

```bash
cd support_queue
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The application creates `support_queue.db` in the repository directory when it starts. The database and local virtual environment are ignored by Git.

## Run the backend

```bash
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Swagger UI is at `/docs` and the OpenAPI document is at `/openapi.json`.

## Backend tests

```bash
pytest -q
```

The tests use isolated in-memory SQLite databases and do not modify the development database.

## Backend API

### Tickets and agents

- `POST /tickets` creates a ticket. Required fields are `subject`, `customer_name`, and `priority` (`urgent` or `normal`). Optional fields include `description`, `status`, `assigned_to`, and timezone-aware `due_at`. If `due_at` is omitted, it is calculated from the priority SLA.
- `GET /tickets/{ticket_id}` retrieves a ticket and returns `404` if it does not exist.
- `PATCH /tickets/{ticket_id}` updates supplied fields and validates priority and status values.
- `POST /tickets/{ticket_id}/assign` assigns an existing agent with `{"agent_id": 1}`.
- `POST /agents` creates an agent with `{"name": "Alex Agent"}`.
- `GET /agents` lists agents in ID order.

### Queue

`GET /tickets/queue` returns active `open` and `in_progress` tickets. Supported query parameters are:

- `overdue=true|false` filters by current overdue status.
- `assigned_to=Agent%20Name` filters by assigned agent name.
- `customer=partial text` performs case-insensitive partial customer-name matching.
- `page=1` selects a 1-based page.
- `page_size=20` selects 1 to 100 results per page.

Filters are applied before sorting and pagination. Queue ordering is:

1. Overdue open/in-progress tickets first.
2. Urgent before normal within each bucket.
3. Earlier `due_at` first.
4. Earlier `created_at` first.
5. Lower ticket ID as the deterministic final tie-breaker.

An active ticket is overdue only when `due_at < current UTC time`; `due_at == now` is not overdue. Resolved and closed tickets are excluded from the active queue.

Example:

```bash
curl -X POST http://127.0.0.1:8000/tickets \
  -H 'Content-Type: application/json' \
  -d '{"subject":"VPN failure","customer_name":"Acme","priority":"urgent"}'

curl 'http://127.0.0.1:8000/tickets/queue?overdue=false&customer=acme&page=1&page_size=10'
```

## Frontend dashboard

The React dashboard displays the queue in the exact order returned by the backend. It supports overdue, assignee, customer, page, and page-size filters; ticket creation; assignment to existing agents; ticket details; loading, empty, error, success, and responsive states.

Start the backend first, then use a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The dashboard is available at `http://localhost:5173`. By default, Vite proxies `/api/*` to `http://127.0.0.1:8000` and strips the `/api` prefix, so the frontend communicates with the existing FastAPI routes without changing their paths.

To use a different backend URL, create `frontend/.env.local` before starting Vite:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

When `VITE_API_BASE_URL` is set, the frontend calls that URL directly. The backend allows the default local Vite origins through CORS.

Build the frontend for production with:

```bash
cd frontend
npm run build
```

## Debugging and troubleshooting

- Use `/docs` to inspect the backend request and response schemas.
- All supplied datetimes must include a timezone, for example `2026-09-16T12:00:00Z`; values are normalized to UTC.
- Queue overdue status is calculated at request time, not stored as a boolean.
- If the local schema needs to be recreated, stop the backend, remove `support_queue.db`, and start it again. This scoped project does not include migrations.
- If frontend API requests fail, confirm the backend is running on port 8000, the Vite server is running on port 5173, and any `VITE_API_BASE_URL` value is correct.
- If Python imports fail during tests, activate `.venv` and run `pytest -q` from the repository root.

See [REASONING.md](REASONING.md) for design decisions. `AI_LOGS.md` must contain the complete unmodified assessment conversation; any missing transcript portion must be added manually by the candidate.
