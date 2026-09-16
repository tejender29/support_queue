from datetime import datetime, timedelta, timezone

from app.models import Priority, Ticket, TicketStatus
from app.services import calculate_due_at, escalate_overdue_tickets, is_overdue, order_tickets

UTC = timezone.utc
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def ticket(
    ticket_id: int,
    *,
    priority: Priority = Priority.NORMAL,
    status: TicketStatus = TicketStatus.OPEN,
    due_at: datetime,
    created_at: datetime,
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=f"Ticket {ticket_id}",
        customer_name="Customer",
        priority=priority,
        status=status,
        due_at=due_at,
        created_at=created_at,
    )


def test_overdue_ticket_precedes_non_overdue_ticket() -> None:
    tickets = [
        ticket(2, due_at=NOW + timedelta(minutes=1), created_at=NOW),
        ticket(1, due_at=NOW - timedelta(minutes=1), created_at=NOW),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [1, 2]


def test_urgent_precedes_normal_within_each_bucket() -> None:
    tickets = [
        ticket(1, priority=Priority.NORMAL, due_at=NOW - timedelta(minutes=2), created_at=NOW),
        ticket(2, priority=Priority.URGENT, due_at=NOW - timedelta(minutes=1), created_at=NOW),
        ticket(3, priority=Priority.NORMAL, due_at=NOW + timedelta(minutes=2), created_at=NOW),
        ticket(4, priority=Priority.URGENT, due_at=NOW + timedelta(minutes=1), created_at=NOW),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [2, 1, 4, 3]


def test_queue_priority_order_is_urgent_high_then_normal() -> None:
    tickets = [
        ticket(1, priority=Priority.NORMAL, due_at=NOW - timedelta(minutes=1), created_at=NOW),
        ticket(2, priority=Priority.HIGH, due_at=NOW - timedelta(minutes=1), created_at=NOW),
        ticket(3, priority=Priority.URGENT, due_at=NOW - timedelta(minutes=1), created_at=NOW),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [3, 2, 1]


def test_earliest_due_at_breaks_priority_ties() -> None:
    tickets = [
        ticket(1, due_at=NOW + timedelta(hours=2), created_at=NOW),
        ticket(2, due_at=NOW + timedelta(hours=1), created_at=NOW),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [2, 1]


def test_created_at_is_final_tie_breaker() -> None:
    due_at = NOW + timedelta(hours=1)
    tickets = [
        ticket(1, due_at=due_at, created_at=NOW + timedelta(minutes=2)),
        ticket(2, due_at=due_at, created_at=NOW + timedelta(minutes=1)),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [2, 1]


def test_ticket_due_exactly_at_request_time_is_not_overdue() -> None:
    tickets = [
        ticket(1, due_at=NOW, created_at=NOW - timedelta(hours=1)),
        ticket(2, due_at=NOW + timedelta(minutes=1), created_at=NOW - timedelta(hours=2)),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [1, 2]


def test_ticket_is_overdue_just_after_due_at() -> None:
    item = ticket(1, due_at=NOW, created_at=NOW - timedelta(hours=1))

    assert is_overdue(item, NOW) is False
    assert is_overdue(item, NOW + timedelta(microseconds=1)) is True


def test_escalation_raises_each_eligible_ticket_by_one_level() -> None:
    tickets = [
        ticket(1, priority=Priority.NORMAL, due_at=NOW - timedelta(minutes=1), created_at=NOW),
        ticket(2, priority=Priority.HIGH, due_at=NOW - timedelta(minutes=1), created_at=NOW),
        ticket(3, priority=Priority.URGENT, due_at=NOW - timedelta(minutes=1), created_at=NOW),
    ]

    escalated = escalate_overdue_tickets(tickets, NOW)

    assert [item.id for item in escalated] == [1, 2]
    assert [item.priority for item in tickets] == [Priority.HIGH, Priority.URGENT, Priority.URGENT]


def test_escalation_does_not_change_non_breached_or_inactive_tickets() -> None:
    due_at = NOW
    tickets = [
        ticket(1, due_at=due_at, created_at=NOW),
        ticket(2, due_at=NOW - timedelta(minutes=1), status=TicketStatus.RESOLVED, created_at=NOW),
        ticket(3, due_at=NOW - timedelta(minutes=1), status=TicketStatus.CLOSED, created_at=NOW),
    ]

    assert escalate_overdue_tickets(tickets, NOW) == []
    assert [item.priority for item in tickets] == [Priority.NORMAL] * 3


def test_repeated_escalation_runs_progress_one_level_and_preserve_due_at() -> None:
    due_at = NOW - timedelta(minutes=1)
    item = ticket(1, due_at=due_at, created_at=NOW)

    assert [item.id for item in escalate_overdue_tickets([item], NOW)] == [1]
    assert item.priority is Priority.HIGH
    assert item.due_at == due_at
    assert [item.id for item in escalate_overdue_tickets([item], NOW)] == [1]
    assert item.priority is Priority.URGENT
    assert item.due_at == due_at
    assert escalate_overdue_tickets([item], NOW) == []


def test_same_due_and_created_times_use_id_for_deterministic_ordering() -> None:
    due_at = NOW + timedelta(hours=1)
    created_at = NOW - timedelta(hours=1)
    tickets = [
        ticket(20, priority=Priority.URGENT, due_at=due_at, created_at=created_at),
        ticket(10, priority=Priority.URGENT, due_at=due_at, created_at=created_at),
    ]

    assert [item.id for item in order_tickets(tickets, NOW)] == [10, 20]


def test_sla_due_at_uses_utc_and_priority_duration() -> None:
    created_at = datetime(2026, 1, 1, 7, 0, tzinfo=timezone(timedelta(hours=-5)))

    assert calculate_due_at(created_at, Priority.URGENT) == datetime(
        2026, 1, 1, 14, 0, tzinfo=UTC
    )
    assert calculate_due_at(created_at, Priority.NORMAL) == datetime(
        2026, 1, 2, 12, 0, tzinfo=UTC
    )
