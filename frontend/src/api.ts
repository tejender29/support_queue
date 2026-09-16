export type Priority = "urgent" | "normal";
export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";

export interface Ticket {
  id: number;
  subject: string;
  description: string | null;
  customer_name: string;
  priority: Priority;
  assigned_to: string | null;
  status: TicketStatus;
  created_at: string;
  due_at: string;
  updated_at: string;
}

export interface Agent {
  id: number;
  name: string;
}

export interface TicketPage {
  items: Ticket[];
  page: number;
  page_size: number;
  total: number;
}

export interface QueueFilters {
  overdue: "" | "true" | "false";
  assigned_to: string;
  customer: string;
  page: number;
  page_size: number;
}

const configuredBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
const apiBase = configuredBase ?? "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status when the server response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function getQueue(filters: QueueFilters): Promise<TicketPage> {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.page_size),
  });
  if (filters.overdue) params.set("overdue", filters.overdue);
  if (filters.assigned_to) params.set("assigned_to", filters.assigned_to);
  if (filters.customer) params.set("customer", filters.customer);
  return request<TicketPage>(`/tickets/queue?${params.toString()}`);
}

export function getAgents(): Promise<Agent[]> {
  return request<Agent[]>("/agents");
}

export function createTicket(payload: {
  subject: string;
  customer_name: string;
  priority: Priority;
  status: TicketStatus;
  assigned_to?: string;
}): Promise<Ticket> {
  return request<Ticket>("/tickets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function assignTicket(ticketId: number, agentId: number): Promise<Ticket> {
  return request<Ticket>(`/tickets/${ticketId}/assign`, {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId }),
  });
}

export function getTicket(ticketId: number): Promise<Ticket> {
  return request<Ticket>(`/tickets/${ticketId}`);
}