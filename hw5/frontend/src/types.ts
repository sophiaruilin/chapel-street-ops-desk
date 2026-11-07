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
  created_at: string
  team_run_id: string | null
  ticket_id: number | null
  agent: Role | null
  tool: 'pay_invoice' | 'pay_rent' | 'order_stock' | 'set_bulk_price' | string
  args: Record<string, unknown>
  kind: 'payment' | 'purchase' | 'price'
  payee: string | null
  amount: number
  memo: string | null
  due: string | null
  status: 'pending' | 'partially_approved' | 'approved' | 'declined' | 'failed'
  first_approver: string | null
  approved_by: string | null
  decided_at: string | null
  reason: string | null
  result: Record<string, unknown> | null
  needs_two_approvers: boolean
}

export interface Draft {
  id: number
  audience: 'customer' | 'internal'
  text: string
  desk_date: string | null
  sent: number
}

export interface TicketDetail extends Omit<Ticket, 'state' | 'pending_approvals'> {
  notes: string | null
  drafts: Draft[]
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  date_today: string
  opening_balance?: number
  paid_out?: number
}
