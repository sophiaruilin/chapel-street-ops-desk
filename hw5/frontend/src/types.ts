export type Role = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'
export type TicketStatus = 'open' | 'waiting_approval' | 'blocked' | 'resolved'

export interface Ticket {
  id: number
  type: string
  subject: string
  requester: string
  sku: string | null
  size: string | null
  qty: number | null
  status: TicketStatus
  state: 'open' | 'resolved'
  pending_approvals: number
}

export interface Run {
  team_run_id: string
  ticket_id: number
  status: 'running' | 'finished' | 'failed'
  started: string
  finished: string | null
  report: string | null
  error: string | null
  delegations: number | null
  requests: number | null
  total_tokens: number | null
}

export interface DeskEvent {
  index: number
  ts: string
  team_run_id: string
  agent: Role | null
  depth: number | null
  event: string
  said: string | null
  tools: { tool: string; args: Record<string, unknown> }[]
  tool_results: { tool: string; result: string }[]
}

export interface EventsPage {
  total_events: number
  last_index: number
  events: DeskEvent[]
}

export interface Approval {
  id: string
  created_ts: string
  team_run_id: string
  ticket_id: number | null
  agent: Role
  tool: 'pay_invoice' | 'pay_rent' | string
  args: Record<string, unknown>
  status: 'pending' | 'approved' | 'declined' | 'failed'
  approved_by: string | null
  decided_ts: string | null
  reason: string | null
  result: Record<string, unknown> | null
  preview?: { payee: string; amount: number; memo: string; due: string | null } | null
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  date_today: string
}
