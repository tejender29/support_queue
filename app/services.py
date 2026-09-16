from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Priority, Ticket, TicketStatus

SLA_BY_PRIORITY = {
    Priority.URGENT: timedelta(hours=2),
    Priority.HIGH: timedelta(hours=8),
    Priority.NORMAL: timedelta(hours=24),
}

PRIORITY_RANK = {
    Priority.URGENT: 0,
    Priority.HIGH: 1,
    Priority.NORMAL: 2,
}

NEXT_PRIORITY = {
    Priority.NORMAL: Priority.HIGH,
    Priority.HIGH: Priority.URGENT,
    Priority.URGENT: Priority.URGENT,
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


def escalate_overdue_tickets(tickets: list[Ticket], now: datetime) -> list[Ticket]:
    """Escalate each eligible ticket by one priority level for this run."""
    request_time = ensure_utc(now)
    escalated: list[Ticket] = []
    for ticket in tickets:
        if is_overdue(ticket, request_time) and ticket.priority is not Priority.URGENT:
            ticket.priority = NEXT_PRIORITY[ticket.priority]
            escalated.append(ticket)
    return escalated


def queue_sort_key(ticket: Ticket, now: datetime) -> tuple[int, int, datetime, datetime, int]:
    overdue_rank = 0 if is_overdue(ticket, now) else 1
    priority_rank = PRIORITY_RANK[ticket.priority]
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
