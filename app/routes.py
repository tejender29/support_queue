from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Agent, Priority, Ticket, TicketStatus
from app.schemas import (
    AgentCreate,
    AgentRead,
    AssignmentRequest,
    TicketCreate,
    TicketPage,
    TicketRead,
    TicketUpdate,
)
from app.services import calculate_due_at, ensure_utc, is_overdue, order_tickets, utc_now

router = APIRouter()


def ticket_response(ticket: Ticket) -> TicketRead:
    return TicketRead(
        id=ticket.id,
        subject=ticket.title,
        description=ticket.description,
        customer_name=ticket.customer_name,
        priority=ticket.priority,
        assigned_to=ticket.assignee,
        status=ticket.status,
        created_at=ensure_utc(ticket.created_at),
        due_at=ensure_utc(ticket.due_at),
        updated_at=ensure_utc(ticket.updated_at),
    )


def get_ticket_or_404(ticket_id: int, db: Session) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)) -> TicketRead:
    now = utc_now()
    due_at = payload.due_at or calculate_due_at(now, payload.priority)
    ticket = Ticket(
        title=payload.subject,
        description=payload.description,
        customer_name=payload.customer_name,
        assignee=payload.assigned_to,
        priority=payload.priority,
        status=payload.status,
        created_at=now,
        due_at=due_at,
        updated_at=now,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket_response(ticket)


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> AgentRead:
    agent = Agent(name=payload.name)
    db.add(agent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Agent already exists") from None
    db.refresh(agent)
    return agent


@router.get("/agents", response_model=list[AgentRead])
def list_agents(db: Session = Depends(get_db)) -> list[Agent]:
    return list(db.scalars(select(Agent).order_by(Agent.id)))


@router.get("/tickets/queue", response_model=TicketPage)
def ticket_queue(
    overdue: bool | None = None,
    assigned_to: str | None = None,
    customer: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TicketPage:
    statement = select(Ticket).where(
        Ticket.status.in_((TicketStatus.OPEN, TicketStatus.IN_PROGRESS))
    )
    if assigned_to is not None:
        statement = statement.where(Ticket.assignee == assigned_to)
    if customer is not None:
        statement = statement.where(Ticket.customer_name.ilike(f"%{customer}%"))

    tickets = list(db.scalars(statement))
    now = utc_now()
    if overdue is not None:
        tickets = [ticket for ticket in tickets if is_overdue(ticket, now) is overdue]
    ordered = order_tickets(tickets, now)
    total = len(ordered)
    start = (page - 1) * page_size
    items = ordered[start : start + page_size]
    return TicketPage(
        items=[ticket_response(ticket) for ticket in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)) -> TicketRead:
    return ticket_response(get_ticket_or_404(ticket_id, db))


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db)
) -> TicketRead:
    ticket = get_ticket_or_404(ticket_id, db)
    changes = payload.model_dump(exclude_unset=True)
    priority_changed = "priority" in changes and changes["priority"] != ticket.priority

    if "subject" in changes:
        ticket.title = changes["subject"]
    if "description" in changes:
        ticket.description = changes["description"]
    if "customer_name" in changes:
        ticket.customer_name = changes["customer_name"]
    if "priority" in changes:
        ticket.priority = changes["priority"]
    if "status" in changes:
        ticket.status = changes["status"]
    if "assigned_to" in changes:
        ticket.assignee = changes["assigned_to"]
    if "due_at" in changes:
        if changes["due_at"] is None:
            raise HTTPException(status_code=422, detail="due_at cannot be null")
        ticket.due_at = ensure_utc(changes["due_at"])
    elif priority_changed:
        ticket.due_at = calculate_due_at(ticket.created_at, ticket.priority)
    ticket.updated_at = utc_now()
    db.commit()
    db.refresh(ticket)
    return ticket_response(ticket)


@router.post("/tickets/{ticket_id}/assign", response_model=TicketRead)
def assign_ticket(
    ticket_id: int, payload: AssignmentRequest, db: Session = Depends(get_db)
) -> TicketRead:
    ticket = get_ticket_or_404(ticket_id, db)
    agent = db.get(Agent, payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    ticket.assignee = agent.name
    ticket.updated_at = utc_now()
    db.commit()
    db.refresh(ticket)
    return ticket_response(ticket)