// The desk talks only to the FastAPI backend from Problem 7.
import type { Approval, Cash, EventsPage, Run, Ticket, TicketDetail } from './types'

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  tickets: () => call<Ticket[]>('/api/tickets'),
  ticket: (id: number) => call<TicketDetail>(`/api/tickets/${id}`),
  runTicket: (id: number) => call<Run>(`/api/tickets/${id}/run`, { method: 'POST' }),
  setStatus: (id: number, status: Ticket['status'], by: string) =>
    call<{ updated: boolean }>(`/api/tickets/${id}/status`, { method: 'POST', body: JSON.stringify({ status, by }) }),
  run: (runId: string) => call<Run>(`/api/runs/${runId}`),
  latestRun: () => call<Run | null>('/api/runs/latest'),
  lastRunFor: (ticketId: number) => call<Run | null>(`/api/tickets/${ticketId}/last_run`),
  events: (runId: string, since?: number) =>
    call<EventsPage>(`/api/events?limit=500&team_run_id=${runId}${since !== undefined ? `&since=${since}` : ''}`),
  approvals: () => call<Approval[]>('/api/approvals'),
  approve: (id: string, approvedBy: string, pin: string) =>
    call<{ done: boolean; paid: boolean; result: Record<string, unknown>; approval: Approval }>(
      `/api/approvals/${id}/approve`,
      { method: 'POST', body: JSON.stringify({ approved_by: approvedBy, pin }) },
    ),
  decline: (id: string, declinedBy: string, pin: string, reason: string) =>
    call<{ done: boolean; approval: Approval }>(`/api/approvals/${id}/decline`, {
      method: 'POST',
      body: JSON.stringify({ declined_by: declinedBy, pin, reason }),
    }),
  cash: () => call<Cash>('/api/cash'),
  reset: (pin: string) => call<{ reset: boolean }>('/api/reset', { method: 'POST', body: JSON.stringify({ pin }) }),
}
