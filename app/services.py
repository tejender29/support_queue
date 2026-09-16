from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Priority, Ticket, TicketStatus

SLA_BY_PRIORITY = {
    Priority.URGENT: timedelta(hours=2),
    Priority.NORMAL: timedelta(hours=24),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def calculate_due_at(created_at: datetime, priority: Priority) -> datetime:
    return ensure_utc(created_at) + SLA_BY_PRIORITY[priority]


def is_overdue(ticket: Ticket, now: datetime) -> bool:
    request_time = ensure_utc(now)
    return (
        ticket.status in {TicketStatus.OPEN, TicketStatus.IN_PROGRESS}
        and ensure_utc(ticket.due_at) < request_time
    )


def queue_sort_key(ticket: Ticket, now: datetime) -> tuple[int, int, datetime, datetime, int]:
    overdue_rank = 0 if is_overdue(ticket, now) else 1
    priority_rank = 0 if ticket.priority is Priority.URGENT else 1
    return (
        overdue_rank,
        priority_rank,
        ensure_utc(ticket.due_at),
        ensure_utc(ticket.created_at),
        ticket.id,
    )


def order_tickets(tickets: list[Ticket], now: datetime) -> list[Ticket]:
    ensure_utc(now)
    return sorted(tickets, key=lambda ticket: queue_sort_key(ticket, now))
