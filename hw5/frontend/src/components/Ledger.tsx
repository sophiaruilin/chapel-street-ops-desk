import { useEffect, useRef, useState } from 'react'
import { money } from '../agents'
import type { Approval, Cash } from '../types'

// The brass cash ledger: the checking balance counts down when a signed payment clears,
// a red "PAID" stamp shows the drop, and a gauge shows what's left of the opening balance.
export default function Ledger({ cash, opening, paid }: { cash: Cash | null; opening: number | null; paid: Approval[] }) {
  const balance = cash?.balance ?? 0
  const shown = useCountTo(cash ? balance : null)
  const [drop, setDrop] = useState<{ amount: number; key: number } | null>(null)
  const prev = useRef<number | null>(null)

  useEffect(() => {
    if (cash == null) return
    if (prev.current != null && cash.balance < prev.current) {
      setDrop({ amount: prev.current - cash.balance, key: Date.now() })
    }
    prev.current = cash.balance
  }, [cash])

  const pct = opening ? Math.max(0, Math.min(100, (balance / opening) * 100)) : 100
  return (
    <section className="ledger" aria-label="Checking balance">
      <div className="ledger-kicker">Checking account <span className="practice">practice ledger · no real money</span></div>
      <div className="ledger-balance" aria-live="polite">
        {cash ? money(shown) : '—'}
        {drop && <span key={drop.key} className="paid-stamp">−{money(drop.amount)} · PAID</span>}
      </div>
      <div className="gauge" title={opening ? `${pct.toFixed(0)}% of the ${money(opening)} opening balance` : ''}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <div className="ledger-meta">
        {opening != null && <>opened at {money(opening)} · </>}as of {cash?.as_of ?? '…'} · cash only goes out
      </div>
      {paid.length > 0 && (
        <ul className="ledger-lines">
          {paid.map((p) => (
            <li key={p.id}>
              <span>{p.tool === 'pay_rent' ? `Rent · lease ${p.args.lease_id}` : p.tool === 'order_stock' ? `Order · ${p.args.qty} × ${p.args.sku}` : `Invoice ${p.args.invoice_id}`}</span>
              <span className="neg">−{money(Number(p.result?.amount ?? 0))}</span>
              <small>signed by {p.approved_by}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// Rolls the number to a new balance. The first known balance is shown immediately (no roll up from
// $0.00); only later changes, like a cleared payment, animate.
function useCountTo(target: number | null) {
  const [v, setV] = useState(target ?? 0)
  const from = useRef<number | null>(target)
  useEffect(() => {
    if (target == null) return
    if (from.current == null) {
      from.current = target
      setV(target)
      return
    }
    const start = performance.now()
    const a = from.current
    let raf = 0
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / 1100)
      const eased = 1 - Math.pow(1 - k, 3)
      setV(a + (target - a) * eased)
      if (k < 1) raf = requestAnimationFrame(step)
      else from.current = target
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target])
  return v
}
