from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

UTC = timezone.utc


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_ticket(client: TestClient, **overrides: object) -> dict:
    payload = {
        "subject": "Cannot log in",
        "description": "Login fails",
        "customer_name": "Acme Corporation",
        "priority": "normal",
        **overrides,
    }
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_ticket(client: TestClient) -> None:
    created = create_ticket(client, priority="urgent")

    assert created["subject"] == "Cannot log in"
    assert created["status"] == "open"
    assert created["assigned_to"] is None
    assert datetime.fromisoformat(created["due_at"]) - datetime.fromisoformat(
        created["created_at"]
    ) == timedelta(hours=2)

    response = client.get(f"/tickets/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_high_priority_is_valid_and_gets_eight_hour_default_sla(client: TestClient) -> None:
    created = create_ticket(client, priority="high")

    assert created["priority"] == "high"
    assert datetime.fromisoformat(created["due_at"]) - datetime.fromisoformat(
        created["created_at"]
    ) == timedelta(hours=8)


def test_update_ticket_changes_fields_and_updated_at(client: TestClient) -> None:
    created = create_ticket(client)

    response = client.patch(
        f"/tickets/{created['id']}",
        json={"subject": "Password reset", "status": "in_progress"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["subject"] == "Password reset"
    assert updated["status"] == "in_progress"
    assert updated["updated_at"] >= created["updated_at"]


def test_priority_update_preserves_agreed_due_at(client: TestClient) -> None:
    created = create_ticket(client, due_at="2020-01-01T00:00:00Z")

    response = client.patch(f"/tickets/{created['id']}", json={"priority": "high"})

    assert response.status_code == 200
    assert response.json()["priority"] == "high"
    assert response.json()["due_at"] == created["due_at"]


def test_assign_ticket_and_list_agents(client: TestClient) -> None:
    agent_response = client.post("/agents", json={"name": "Alex Agent"})
    assert agent_response.status_code == 201
    agent = agent_response.json()
    ticket = create_ticket(client)

    response = client.post(
        f"/tickets/{ticket['id']}/assign", json={"agent_id": agent["id"]}
    )

    assert response.status_code == 200
    assert response.json()["assigned_to"] == "Alex Agent"
    assert client.get("/agents").json() == [agent]


def test_queue_ordering_and_active_status_filter(client: TestClient) -> None:
    create_ticket(
        client,
        subject="Future normal",
        priority="normal",
        due_at="2099-01-01T00:00:00Z",
    )
    create_ticket(
        client,
        subject="Overdue normal",
        priority="normal",
        due_at="2020-01-01T00:00:00Z",
    )
    create_ticket(
        client,
        subject="Overdue urgent",
        priority="urgent",
        due_at="2020-01-01T00:00:00Z",
    )
    create_ticket(
        client,
        subject="Resolved overdue",
        status="resolved",
        due_at="2020-01-01T00:00:00Z",
    )
    create_ticket(
        client,
        subject="Closed future",
        status="closed",
        due_at="2099-01-01T00:00:00Z",
    )

    response = client.get("/tickets/queue")

    assert response.status_code == 200
    assert [item["subject"] for item in response.json()["items"]] == [
        "Overdue urgent",
        "Overdue normal",
        "Future normal",
    ]
    assert response.json()["total"] == 3


def test_queue_orders_urgent_before_high_before_normal(client: TestClient) -> None:
    for priority in ("normal", "high", "urgent"):
        create_ticket(client, priority=priority, due_at="2020-01-01T00:00:00Z")

    response = client.get("/tickets/queue")

    assert [item["priority"] for item in response.json()["items"]] == [
        "urgent",
        "high",
        "normal",
    ]


def test_escalation_endpoint_progresses_one_level_per_run(client: TestClient) -> None:
    normal = create_ticket(client, priority="normal", due_at="2020-01-01T00:00:00Z")
    high = create_ticket(client, priority="high", due_at="2020-01-01T00:00:00Z")
    urgent = create_ticket(client, priority="urgent", due_at="2020-01-01T00:00:00Z")
    current = create_ticket(client, priority="normal", due_at="2099-01-01T00:00:00Z")
    resolved = create_ticket(
        client, priority="normal", status="resolved", due_at="2020-01-01T00:00:00Z"
    )
    closed = create_ticket(
        client, priority="normal", status="closed", due_at="2020-01-01T00:00:00Z"
    )

    first = client.post("/tickets/escalate")
    assert first.status_code == 200
    assert first.json()["ticket_ids"] == [normal["id"], high["id"]]
    assert first.json()["escalated_count"] == 2
    assert client.get(f"/tickets/{normal['id']}").json()["priority"] == "high"
    assert client.get(f"/tickets/{high['id']}").json()["priority"] == "urgent"
    assert client.get(f"/tickets/{urgent['id']}").json()["priority"] == "urgent"
    assert client.get(f"/tickets/{current['id']}").json()["priority"] == "normal"
    assert client.get(f"/tickets/{resolved['id']}").json()["priority"] == "normal"
    assert client.get(f"/tickets/{closed['id']}").json()["priority"] == "normal"

    second = client.post("/tickets/escalate")
    assert second.json()["ticket_ids"] == [normal["id"]]
    assert client.get(f"/tickets/{normal['id']}").json()["priority"] == "urgent"
    assert client.get(f"/tickets/{normal['id']}").json()["due_at"] == normal["due_at"]

    assert client.post("/tickets/escalate").json() == {
        "escalated_count": 0,
        "ticket_ids": [],
    }


def test_queue_overdue_filter(client: TestClient) -> None:
    create_ticket(client, subject="Overdue", due_at="2020-01-01T00:00:00Z")
    create_ticket(client, subject="Not overdue", due_at="2099-01-01T00:00:00Z")

    response = client.get("/tickets/queue", params={"overdue": "true"})

    assert response.status_code == 200
    assert [item["subject"] for item in response.json()["items"]] == ["Overdue"]

    response = client.get("/tickets/queue", params={"overdue": "false"})

    assert response.status_code == 200
    assert [item["subject"] for item in response.json()["items"]] == ["Not overdue"]


def test_queue_assignee_and_customer_search_filters(client: TestClient) -> None:
    agent_response = client.post("/agents", json={"name": "Queue Agent"})
    agent_id = agent_response.json()["id"]
    first = create_ticket(client, customer_name="Northwind Industries")
    create_ticket(client, customer_name="Southwind Industries")
    client.post(f"/tickets/{first['id']}/assign", json={"agent_id": agent_id})

    assigned = client.get("/tickets/queue", params={"assigned_to": "Queue Agent"})
    searched = client.get("/tickets/queue", params={"customer": "NORTH"})

    assert [item["id"] for item in assigned.json()["items"]] == [first["id"]]
    assert [item["customer_name"] for item in searched.json()["items"]] == [
        "Northwind Industries"
    ]


def test_queue_combines_active_status_and_customer_filters(client: TestClient) -> None:
    agent_response = client.post("/agents", json={"name": "Combined Agent"})
    agent_id = agent_response.json()["id"]
    matching = create_ticket(
        client,
        customer_name="Example Support Customer",
        status="in_progress",
        due_at="2099-01-01T00:00:00Z",
    )
    client.post(f"/tickets/{matching['id']}/assign", json={"agent_id": agent_id})
    create_ticket(
        client,
        customer_name="Example Support Customer",
        status="resolved",
        due_at="2099-01-01T00:00:00Z",
    )

    response = client.get(
        "/tickets/queue",
        params={"assigned_to": "Combined Agent", "customer": "SUPPORT"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [matching["id"]]


def test_queue_pagination_is_applied_after_ordering(client: TestClient) -> None:
    for index in range(3):
        create_ticket(
            client,
            subject=f"Ticket {index}",
            due_at=f"2099-01-0{index + 1}T00:00:00Z",
        )

    response = client.get("/tickets/queue", params={"page": 2, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert [item["subject"] for item in body["items"]] == ["Ticket 2"]


def test_empty_queue_returns_empty_page(client: TestClient) -> None:
    response = client.get("/tickets/queue")

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_page_beyond_available_results_returns_empty_items(client: TestClient) -> None:
    create_ticket(client)

    response = client.get("/tickets/queue", params={"page": 2, "page_size": 1})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 1


def test_invalid_ids_and_payload_values_are_rejected(client: TestClient) -> None:
    assert client.get("/tickets/999").status_code == 404
    assert client.patch("/tickets/999", json={"status": "open"}).status_code == 404
    assert client.post("/tickets", json={
        "subject": "Bad priority",
        "customer_name": "Customer",
        "priority": "critical",
    }).status_code == 422
    assert client.post("/tickets", json={
        "subject": "Bad status",
        "customer_name": "Customer",
        "priority": "normal",
        "status": "waiting",
    }).status_code == 422
    assert client.get("/tickets/queue", params={"page": 0}).status_code == 422
    assert client.get("/tickets/queue", params={"page_size": 101}).status_code == 422
    assert client.post("/tickets", json={
        "subject": "Missing customer",
        "priority": "normal",
    }).status_code == 422
    assert client.post("/tickets", json={
        "subject": "Naive due date",
        "customer_name": "Customer",
        "priority": "normal",
        "due_at": "2099-01-01T00:00:00",
    }).status_code == 422

    ticket = create_ticket(client)
    assert client.patch(f"/tickets/{ticket['id']}", json={"due_at": None}).status_code == 422


def test_unassigned_agent_returns_404(client: TestClient) -> None:
    ticket = create_ticket(client)

    response = client.post(f"/tickets/{ticket['id']}/assign", json={"agent_id": 999})

    assert response.status_code == 404
