import { useState } from 'react'
import { AGENTS, money } from '../agents'
import type { Approval } from '../types'

interface Props {
  pending: Approval[]
  signer: string
  onSigner: (s: string) => void
  pin: string
  onPin: (s: string) => void
  onApprove: (a: Approval) => Promise<void>
  onDecline: (a: Approval, reason: string) => Promise<void>
}

const TOOL_TITLE: Record<string, string> = {
  pay_invoice: 'Vendor invoice',
  pay_rent: 'Rent',
  order_stock: 'Purchase order',
  set_bulk_price: 'Bulk price',
}

// "Needs your signature": everything the agents PREPARED (payments, purchase orders, bulk prices).
// The payee and amount on each card were frozen by the MCP server when the agent prepared it.
// Nothing happens until a person signs with the desk PIN, and a cheque can't be cashed twice.
export default function ApprovalTray({ pending, signer, onSigner, pin, onPin, onApprove, onDecline }: Props) {
  return (
    <section className="tray" aria-label="Approvals awaiting your signature">
      <h2 className="panel-title">Signature tray <small>{pending.length ? `${pending.length} waiting` : 'all clear'}</small></h2>
      <div className="signer-card">
        <label>
          <span className="cheque-label">Signing as</span>
          <input className="signer-name" value={signer} onChange={(e) => onSigner(e.target.value)} placeholder="Your full name" autoComplete="name" />
        </label>
        <label>
          <span className="cheque-label">Desk PIN</span>
          <input className="signer-pin" type="password" inputMode="numeric" value={pin} onChange={(e) => onPin(e.target.value)} placeholder="from .env" autoComplete="off" />
        </label>
        <p className="practice-note">Practice ledger: signing changes the shop's SQLite file, never a real bank or card.</p>
      </div>
      {pending.length === 0 && (
        <p className="tray-empty">Nothing to sign. When an agent prepares a payment, purchase or price, it lands here and waits for you.</p>
      )}
      {pending.map((p) => (
        <ApprovalCard key={p.id} p={p} canSign={signer.trim().length >= 2 && pin.trim().length > 0}
          onApprove={onApprove} onDecline={onDecline} />
      ))}
    </section>
  )
}

function ApprovalCard({ p, canSign, onApprove, onDecline }: {
  p: Approval; canSign: boolean; onApprove: Props['onApprove']; onDecline: Props['onDecline']
}) {
  const [busy, setBusy] = useState(false)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const isPrice = p.kind === 'price'

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <article className={`cheque ${isPrice ? 'cheque-price' : ''}`}>
      <div className="cheque-top">
        <span>{TOOL_TITLE[p.tool] ?? p.tool} · ticket {p.ticket_id ?? '—'}</span>
        <span>No. {p.id}</span>
      </div>
      <div className="cheque-pay">
        <span className="cheque-label">{isPrice ? 'Approve a bulk price for' : 'Pay to the order of'}</span>
        <b>{p.payee ?? '—'}</b>
        <span className="cheque-amount">{money(p.amount)}</span>
      </div>
      <div className="cheque-memo">
        <span className="cheque-label">Memo</span> {p.memo}
        {p.due && <> · {p.kind === 'purchase' ? 'expected' : 'due'} {p.due}</>}
        <span className="cheque-from"> · prepared by {p.agent ? AGENTS[p.agent].name : 'the desk'}</span>
      </div>
      {p.needs_two_approvers && (
        <p className="two-sig">
          ✒✒ Over the two-signature limit:{' '}
          {p.status === 'partially_approved' ? <>signed by <b>{p.first_approver}</b>, needs a second, different person</> : 'needs two different people'}
        </p>
      )}
      {error && <p className="cheque-error">{error}</p>}
      {declining ? (
        <div className="cheque-actions">
          <input className="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" />
          <button className="btn btn-ghost" disabled={busy || !canSign} onClick={() => run(() => onDecline(p, reason))}>Confirm decline</button>
          <button className="btn btn-link" onClick={() => setDeclining(false)}>back</button>
        </div>
      ) : (
        <div className="cheque-actions">
          <button className="btn btn-sign" disabled={!canSign || busy} onClick={() => run(() => onApprove(p))}
            title={canSign ? '' : 'Enter your name and the desk PIN above'}>
            {busy ? 'Clearing…' : isPrice ? 'Approve price' : p.kind === 'purchase' ? 'Sign & order' : 'Sign & pay'}
          </button>
          <button className="btn btn-ghost" disabled={busy} onClick={() => setDeclining(true)}>Decline</button>
        </div>
      )}
    </article>
  )
}
