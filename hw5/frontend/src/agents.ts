import type { Role } from './types'

// Each agent has its own seat, colour and "voice" (how its words are typeset on the wire).
export interface AgentMeta {
  role: Role
  name: string
  title: string
  monogram: string
  color: string
  voice: 'memo' | 'tag' | 'ledger' | 'notice' | 'note'
  voiceLabel: string
}

export const AGENTS: Record<Role, AgentMeta> = {
  boss: {
    role: 'boss', name: 'The Boss', title: 'Runs the desk', monogram: 'B',
    color: '#00356b', voice: 'memo', voiceLabel: 'memo from the desk',
  },
  inventory: {
    role: 'inventory', name: 'Inventory', title: 'Stockroom & vendors', monogram: 'I',
    color: '#2e6b4f', voice: 'tag', voiceLabel: 'stockroom tag',
  },
  accounting: {
    role: 'accounting', name: 'Accounting', title: 'Cash & payments', monogram: 'A',
    color: '#8c6c3c', voice: 'ledger', voiceLabel: 'ledger entry',
  },
  facilities: {
    role: 'facilities', name: 'Facilities', title: 'Lease & landlord', monogram: 'F',
    color: '#8a2d3b', voice: 'notice', voiceLabel: 'building notice',
  },
  customer_service: {
    role: 'customer_service', name: 'Customer Service', title: 'Drafts & replies', monogram: 'C',
    color: '#286dc0', voice: 'note', voiceLabel: 'handwritten note',
  },
}

export const SPECIALISTS: Role[] = ['inventory', 'accounting', 'facilities', 'customer_service']
export const ROLES: Role[] = ['boss', ...SPECIALISTS]

// Friendly labels for MCP tools, shown on the little brass tool chips.
export const TOOL_LABELS: Record<string, string> = {
  get_desk_date: 'desk date',
  list_open_tickets: 'ticket board',
  list_tickets: 'ticket board',
  get_ticket: 'read ticket',
  update_ticket_status: 'set status',
  check_stock_by_sku_and_size: 'check shelf',
  list_vendors: 'vendor list',
  list_open_invoices: 'open invoices',
  get_cash_balances: 'cash balance',
  get_sku_cost_and_price: 'cost & price',
  list_payments: 'payment history',
  pay_invoice: 'pay invoice',
  pay_rent: 'pay rent',
  get_lease_rent_and_cash: 'lease & cash',
  add_ticket_draft: 'save draft',
  ask_teammate: 'ask teammate',
}

export const STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  waiting_approval: 'Awaiting signature',
  blocked: 'Blocked',
  resolved: 'Resolved',
}

export const TICKET_KIND: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
