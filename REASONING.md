# Design Reasoning

## Interpretation

The problem is a small support-ticket API whose central behavior is a live SLA-aware queue. The implementation stays intentionally narrow: tickets can be created, retrieved, updated, and assigned; agents are a minimal directory; the queue supports the required filters and pagination. Authentication, authorization, migrations, and background workers are outside the scope.

## Data model and API mapping

`Ticket` stores an ID, subject, description, customer name, priority, status, assignee name, `created_at`, `updated_at`, and `due_at`. The database model retains the original internal names `title` and `assignee`, while the public Pydantic API exposes `subject` and `assigned_to` to match the API contract. `Agent` contains only a unique ID and name.

Valid priorities are `urgent` and `normal`. Valid statuses are `open`, `in_progress`, `resolved`, and `closed`. The API validates these values through Pydantic enums.

## SLA and overdue policy

Urgent tickets receive a two-hour response SLA; normal tickets receive 24 hours. When `due_at` is omitted, it is calculated from the UTC-normalized creation time. A ticket is overdue exactly when it is `open` or `in_progress` and `due_at < now`. Therefore `due_at == now` is not overdue, while any instant just after `due_at` is overdue. Resolved and closed tickets are never considered overdue for the active queue.

The queue computes this status using the current UTC time for each request rather than storing an `overdue` flag. This prevents a stored status from becoming stale as time passes and makes filters reflect the moment the queue is requested.

## Queue ordering

The pure `order_tickets` service sorts by these keys, in order:

1. Overdue bucket: overdue first.
2. Priority: urgent before normal.
3. Earlier `due_at` first.
4. Earlier `created_at` first.
5. Lower ticket ID as a deterministic final tie-breaker when all required keys match.

The final ID key does not change the stated business ordering; it only removes dependence on database return order for otherwise identical tickets.

## Time and persistence

All application timestamps must be timezone-aware and are normalized to UTC. SQLite does not preserve timezone metadata in its native datetime storage, so the SQLAlchemy `UTCDateTime` type stores UTC values and restores UTC awareness when reading them. A small SQLAlchemy session dependency scopes each request's database work.

## Filtering and pagination

The queue first restricts results to `open` and `in_progress` tickets, then applies database-friendly assignee and case-insensitive partial customer-name filters. Overdue filtering is applied in Python using the request-time UTC clock. The remaining tickets are sorted by the shared queue function and sliced for 1-based pagination. `page_size` is limited to 1 through 100, and an empty or out-of-range page returns an empty `items` list with the total count.

## Assumptions and trade-offs

- Assignment stores the agent's name on the ticket rather than adding a foreign key or relationship. This keeps the interview-sized model simple, while the assignment endpoint still validates that the agent exists.
- Updating priority recalculates `due_at` from the original `created_at` unless the request explicitly supplies a new due date. This keeps the SLA consistent with the new priority without changing ticket age.
- SQLite and application-start table creation are appropriate for the scoped assessment. A production deployment would use migrations and a database with stronger concurrency and operational tooling.
- Queue classification and ordering happen in Python after retrieval. This makes request-time clock behavior explicit and readable; a larger system could push more of this work into SQL.

## Testing strategy

Unit tests cover SLA durations, UTC conversion, exact-boundary overdue behavior, just-after-boundary behavior, every queue ordering key, and deterministic ID ordering. API tests cover ticket CRUD, assignment, agent lookup, active-status exclusion, both overdue filter values, assignee and customer filters including combinations and case-insensitive partial matching, pagination including empty pages, validation errors, and missing resources. Tests use isolated in-memory SQLite databases so they do not depend on or alter the local development database.
