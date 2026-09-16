from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Priority, TicketStatus


class TicketBase(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    description: str | None = None
    customer_name: str = Field(min_length=1, max_length=200)
    priority: Priority


class TicketCreate(TicketBase):
    status: TicketStatus = TicketStatus.OPEN
    assigned_to: str | None = Field(default=None, max_length=200)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_at must be timezone-aware")
        return value


class TicketUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=200)
    priority: Priority | None = None
    status: TicketStatus | None = None
    assigned_to: str | None = Field(default=None, max_length=200)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_at must be timezone-aware")
        return value


class TicketRead(TicketBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assigned_to: str | None
    status: TicketStatus
    created_at: datetime
    due_at: datetime
    updated_at: datetime


class AssignmentRequest(BaseModel):
    agent_id: int = Field(gt=0)


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AgentRead(AgentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TicketPage(BaseModel):
    items: list[TicketRead]
    page: int
    page_size: int
    total: int


class EscalationResult(BaseModel):
    escalated_count: int
    ticket_ids: list[int]
