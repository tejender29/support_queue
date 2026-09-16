import { FormEvent, useEffect, useState } from "react";
import {
  Agent,
  assignTicket,
  createTicket,
  getAgents,
  getQueue,
  getTicket,
  Priority,
  QueueFilters,
  Ticket,
  TicketStatus,
} from "./api";

const initialFilters: QueueFilters = {
  overdue: "",
  assigned_to: "",
  customer: "",
  page: 1,
  page_size: 10,
};

const statusLabels: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function isOverdue(ticket: Ticket): boolean {
  return (ticket.status === "open" || ticket.status === "in_progress") &&
    new Date(ticket.due_at).getTime() < Date.now();
}

function App() {
  const [filters, setFilters] = useState(initialFilters);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [details, setDetails] = useState<Ticket | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [assigningId, setAssigningId] = useState<number | null>(null);
  const [form, setForm] = useState({
    subject: "",
    customer_name: "",
    priority: "normal" as Priority,
    status: "open" as TicketStatus,
    assigned_to: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const totalPages = Math.max(1, Math.ceil(total / filters.page_size));

  async function loadQueue(nextFilters = filters) {
    setLoading(true);
    setError("");
    try {
      const result = await getQueue(nextFilters);
      setTickets(result.items);
      setTotal(result.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load queue");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadQueue();
    getAgents().then(setAgents).catch(() => setError("Unable to load agents"));
  }, []);

  function updateFilter<Key extends keyof QueueFilters>(key: Key, value: QueueFilters[Key]) {
    const next = { ...filters, [key]: value, page: 1 };
    setFilters(next);
    void loadQueue(next);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await createTicket({
        ...form,
        ...(form.assigned_to ? { assigned_to: form.assigned_to } : {}),
      });
      setForm({ subject: "", customer_name: "", priority: "normal", status: "open", assigned_to: "" });
      setNotice("Ticket created and queue refreshed.");
      await loadQueue({ ...filters, page: 1 });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create ticket");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAssignment(ticketId: number, agentId: number) {
    setAssigningId(ticketId);
    setError("");
    try {
      await assignTicket(ticketId, agentId);
      setNotice(`Ticket #${ticketId} assigned successfully.`);
      await loadQueue();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to assign ticket");
    } finally {
      setAssigningId(null);
    }
  }

  async function openDetails(ticketId: number) {
    setDetailsLoading(true);
    setError("");
    try {
      setDetails(await getTicket(ticketId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load ticket");
    } finally {
      setDetailsLoading(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">SQ</div>
          <div>
            <p className="eyebrow">Operations console</p>
            <h1>Support Queue</h1>
          </div>
        </div>
        <div className="live-indicator"><span /> Live queue</div>
      </header>

      <main>
        <section className="hero-row">
          <div>
            <p className="eyebrow">Helpdesk / Today</p>
            <h2>Keep every customer moving.</h2>
            <p className="hero-copy">A focused view of active work, sorted by SLA urgency and ready for the next action.</p>
          </div>
          <div className="queue-count"><strong>{total}</strong><span>active tickets</span></div>
        </section>

        {(error || notice) && <div className={`alert ${error ? "alert-error" : "alert-success"}`} role="status">{error || notice}</div>}

        <section className="workspace-grid">
          <div className="queue-panel panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Prioritized work</p><h3>Active queue</h3></div>
              <button className="button button-quiet" onClick={() => void loadQueue()} disabled={loading} title="Refresh queue">↻ Refresh</button>
            </div>
            <div className="filters" aria-label="Queue filters">
              <label>Overdue<select value={filters.overdue} onChange={(event) => updateFilter("overdue", event.target.value as QueueFilters["overdue"])}><option value="">All tickets</option><option value="true">Overdue only</option><option value="false">On track only</option></select></label>
              <label>Assigned to<select value={filters.assigned_to} onChange={(event) => updateFilter("assigned_to", event.target.value)}><option value="">Anyone</option>{agents.map((agent) => <option key={agent.id} value={agent.name}>{agent.name}</option>)}</select></label>
              <label className="search-field">Customer<input value={filters.customer} onChange={(event) => updateFilter("customer", event.target.value)} placeholder="Search customers" /></label>
              <label>Per page<select value={filters.page_size} onChange={(event) => updateFilter("page_size", Number(event.target.value))}><option value={10}>10</option><option value={20}>20</option><option value={50}>50</option></select></label>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Ticket</th><th>Customer</th><th>Priority</th><th>Status</th><th>Due</th><th>Assignee</th><th><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {loading ? <tr><td colSpan={7} className="table-message"><span className="spinner" /> Loading queue...</td></tr> : tickets.length === 0 ? <tr><td colSpan={7} className="table-message"><strong>No tickets match these filters.</strong><span>Try widening your search or add a new ticket.</span></td></tr> : tickets.map((ticket) => {
                    const overdue = isOverdue(ticket);
                    return <tr key={ticket.id} className={overdue ? "row-overdue" : ""}>
                      <td><button className="ticket-link" onClick={() => void openDetails(ticket.id)}>#{ticket.id} <span>{ticket.subject}</span></button></td>
                      <td>{ticket.customer_name}</td>
                      <td><span className={`priority priority-${ticket.priority}`}>{ticket.priority}</span></td>
                      <td><span className={`status status-${ticket.status}`}>{statusLabels[ticket.status]}</span></td>
                      <td><span className={overdue ? "due-overdue" : "due-time"}>{formatDate(ticket.due_at)}</span>{overdue && <small className="overdue-label">Overdue</small>}</td>
                      <td><select className="assign-select" aria-label={`Assign ticket ${ticket.id}`} value={ticket.assigned_to ?? ""} onChange={(event) => { const agent = agents.find((item) => item.name === event.target.value); if (agent) void handleAssignment(ticket.id, agent.id); }} disabled={assigningId === ticket.id}><option value="">Unassigned</option>{agents.map((agent) => <option key={agent.id} value={agent.name}>{agent.name}</option>)}</select></td>
                      <td><button className="icon-button" onClick={() => void openDetails(ticket.id)} title={`View ticket ${ticket.id}`}>→</button></td>
                    </tr>;
                  })}
                </tbody>
              </table>
            </div>
            <div className="pagination"><span>Showing {tickets.length ? (filters.page - 1) * filters.page_size + 1 : 0}–{Math.min(filters.page * filters.page_size, total)} of {total}</span><div><button className="page-button" disabled={filters.page <= 1 || loading} onClick={() => { const next = { ...filters, page: filters.page - 1 }; setFilters(next); void loadQueue(next); }}>Previous</button><span className="page-number">{filters.page} / {totalPages}</span><button className="page-button" disabled={filters.page >= totalPages || loading} onClick={() => { const next = { ...filters, page: filters.page + 1 }; setFilters(next); void loadQueue(next); }}>Next</button></div></div>
          </div>

          <aside className="side-column">
            <section className="panel create-panel"><div className="panel-heading"><div><p className="eyebrow">New work</p><h3>Create ticket</h3></div><span className="plus-mark">+</span></div><form onSubmit={handleCreate}>
              <label>Subject<input required value={form.subject} onChange={(event) => setForm({ ...form, subject: event.target.value })} placeholder="Brief issue summary" /></label>
              <label>Customer name<input required value={form.customer_name} onChange={(event) => setForm({ ...form, customer_name: event.target.value })} placeholder="Company or contact" /></label>
              <div className="form-row"><label>Priority<select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as Priority })}><option value="normal">Normal</option><option value="urgent">Urgent</option></select></label><label>Status<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as TicketStatus })}><option value="open">Open</option><option value="in_progress">In progress</option></select></label></div>
              <label>Assign now<select value={form.assigned_to} onChange={(event) => setForm({ ...form, assigned_to: event.target.value })}><option value="">Leave unassigned</option>{agents.map((agent) => <option key={agent.id} value={agent.name}>{agent.name}</option>)}</select></label>
              <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Creating..." : "Create ticket"}<span>↗</span></button>
            </form></section>
            <section className="side-note"><span className="note-icon">i</span><div><strong>Queue logic</strong><p>Overdue work is surfaced first, followed by urgent priority and earliest due time.</p></div></section>
          </aside>
        </section>
      </main>

      {details && <div className="modal-backdrop" onClick={() => setDetails(null)}><section className="details-drawer" onClick={(event) => event.stopPropagation()}><button className="close-button" onClick={() => setDetails(null)} aria-label="Close ticket details">×</button><p className="eyebrow">Ticket #{details.id}</p><h2>{details.subject}</h2><div className="detail-tags"><span className={`priority priority-${details.priority}`}>{details.priority}</span><span className={`status status-${details.status}`}>{statusLabels[details.status]}</span>{isOverdue(details) && <span className="overdue-chip">Overdue</span>}</div><dl className="detail-list"><div><dt>Customer</dt><dd>{details.customer_name}</dd></div><div><dt>Assigned to</dt><dd>{details.assigned_to ?? "Unassigned"}</dd></div><div><dt>Due</dt><dd>{formatDate(details.due_at)}</dd></div><div><dt>Created</dt><dd>{formatDate(details.created_at)}</dd></div></dl>{details.description && <div className="description"><p className="eyebrow">Description</p><p>{details.description}</p></div>}<button className="button button-quiet drawer-close" onClick={() => setDetails(null)}>{detailsLoading ? "Loading..." : "Close details"}</button></section></div>}
    </div>
  );
}

export default App;