import { useState } from 'react'
import { AGENTS, money } from '../agents'
import type { Approval } from '../types'

interface Props {
  pending: Approval[]
  signer: string
  onSigner: (s: string) => void
  onApprove: (a: Approval) => Promise<void>
  onDecline: (a: Approval, reason: string) => Promise<void>
}

// "Needs your signature": every payment the agents prepared shows up as a cheque.
// Nothing is paid until a person signs; signing is what moves cash.
export default function ApprovalTray({ pending, signer, onSigner, onApprove, onDecline }: Props) {
  return (
    <section className="tray" aria-label="Payments awaiting your signature">
      <h2 className="panel-title">Signature tray <small>{pending.length ? `${pending.length} waiting` : 'all clear'}</small></h2>
      {pending.length === 0 && (
        <p className="tray-empty">No cheques to sign. When an agent prepares a payment, it lands here and waits for you.</p>
      )}
      {pending.map((p) => (
        <Cheque key={p.id} p={p} signer={signer} onSigner={onSigner} onApprove={onApprove} onDecline={onDecline} />
      ))}
    </section>
  )
}

function Cheque({ p, signer, onSigner, onApprove, onDecline }: Omit<Props, 'pending'> & { p: Approval }) {
  const [busy, setBusy] = useState(false)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const pv = p.preview
  const canSign = signer.trim().length >= 2 && !busy

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <article className="cheque">
      <div className="cheque-top">
        <span>Campus Customs · Chapel Street</span>
        <span>No. {p.id}</span>
      </div>
      <div className="cheque-pay">
        <span className="cheque-label">Pay to the order of</span>
        <b>{pv?.payee ?? (p.tool === 'pay_rent' ? `Lease ${p.args.lease_id}` : `Invoice ${p.args.invoice_id}`)}</b>
        <span className="cheque-amount">{pv ? money(pv.amount) : '—'}</span>
      </div>
      <div className="cheque-memo">
        <span className="cheque-label">Memo</span> {pv?.memo ?? p.tool}
        {pv?.due && <> · due {pv.due}</>}
        <span className="cheque-from"> · prepared by {AGENTS[p.agent].name} for ticket {p.ticket_id ?? '—'}</span>
      </div>
      <label className="sign-line">
        <span className="cheque-label">Authorized signature</span>
        <input value={signer} onChange={(e) => onSigner(e.target.value)} placeholder="Sign your full name" autoComplete="name" />
      </label>
      {error && <p className="cheque-error">{error}</p>}
      {declining ? (
        <div className="cheque-actions">
          <input className="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" />
          <button className="btn btn-ghost" disabled={busy} onClick={() => run(() => onDecline(p, reason))}>Confirm decline</button>
          <button className="btn btn-link" onClick={() => setDeclining(false)}>back</button>
        </div>
      ) : (
        <div className="cheque-actions">
          <button className="btn btn-sign" disabled={!canSign} onClick={() => run(() => onApprove(p))}>
            {busy ? 'Clearing…' : 'Sign & pay'}
          </button>
          <button className="btn btn-ghost" disabled={busy} onClick={() => setDeclining(true)}>Decline</button>
        </div>
      )}
    </article>
  )
}
