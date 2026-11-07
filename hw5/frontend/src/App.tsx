import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, API_URL } from './api'
import { STATUS_LABEL, TICKET_KIND, money } from './agents'
import { deriveActivity } from './derive'
import type { Approval, Cash, DeskEvent, Run, Ticket, TicketDetail } from './types'
import TicketRail from './components/TicketRail'
import TeamTable from './components/TeamTable'
import Wire from './components/Wire'
import Summary from './components/Summary'
import ApprovalTray from './components/ApprovalTray'
import Ledger from './components/Ledger'
import DanCorner from './components/DanCorner'

const RUNS_KEY = 'cc-desk-runs'
const SIGNER_KEY = 'cc-desk-signer'
const OPENING_KEY = 'cc-desk-opening'
const PIN_KEY = 'cc-desk-pin' // sessionStorage only: forgotten when the tab closes

type Tab = 'wire' | 'summary'

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [opening, setOpening] = useState<number | null>(() => {
    const v = localStorage.getItem(OPENING_KEY)
    return v ? Number(v) : null
  })
  const [approvals, setApprovals] = useState<Approval[]>([])
  const params = new URLSearchParams(window.location.search)
  const [selectedId, setSelectedId] = useState<number | null>(() => Number(params.get('ticket')) || null)
  const [runs, setRuns] = useState<Record<number, Run>>(() => JSON.parse(localStorage.getItem(RUNS_KEY) ?? '{}'))
  const [events, setEvents] = useState<Record<string, DeskEvent[]>>({})
  const [tab, setTab] = useState<Tab>(() => (params.get('tab') === 'summary' ? 'summary' : 'wire'))
  const [signer, setSigner] = useState(() => localStorage.getItem(SIGNER_KEY) ?? '')
  const [pin, setPin] = useState(() => sessionStorage.getItem(PIN_KEY) ?? '')
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [offline, setOffline] = useState<string | null>(null)
  const [cheer, setCheer] = useState<{ text: string; key: number } | null>(null)
  const lastIndex = useRef<Record<string, number>>({})

  const say = (text: string) => setCheer({ text, key: Date.now() })

  // ---------------------------------------------------------------- board data
  const refreshBoard = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals()])
      setTickets(t)
      setCash(c)
      setApprovals(a)
      setOffline(null)
      setSelectedId((id) => id ?? t[0]?.id ?? null)
      setOpening((o) => {
        if (o != null) return o
        localStorage.setItem(OPENING_KEY, String(c.balance))
        return c.balance
      })
    } catch (e) {
      setOffline((e as Error).message)
    }
  }, [])

  useEffect(() => {
    refreshBoard()
    const t = window.setInterval(refreshBoard, 4000)
    return () => window.clearInterval(t)
  }, [refreshBoard])

  // Pick up a run that was already going when the page loaded.
  useEffect(() => {
    api.latestRun().then((r) => r && setRuns((rs) => ({ ...rs, [r.ticket_id]: r }))).catch(() => {})
  }, [])

  useEffect(() => localStorage.setItem(RUNS_KEY, JSON.stringify(runs)), [runs])
  useEffect(() => localStorage.setItem(SIGNER_KEY, signer), [signer])
  useEffect(() => sessionStorage.setItem(PIN_KEY, pin), [pin])

  const busyRun = useMemo(() => Object.values(runs).find((r) => r.status === 'running') ?? null, [runs])
  const selectedRun = selectedId != null ? runs[selectedId] ?? null : null
  const selectedTicket = tickets.find((t) => t.id === selectedId) ?? null

  useEffect(() => {
    if (selectedId == null) return
    api.ticket(selectedId).then(setDetail).catch(() => setDetail(null))
  }, [selectedId, tickets])

  // A ticket's last run comes back from the audit trail (survives restarts and fresh browsers).
  useEffect(() => {
    if (selectedId == null || runs[selectedId]) return
    api.lastRunFor(selectedId).then((r) => r && setRuns((rs) => ({ ...rs, [r.ticket_id]: r }))).catch(() => {})
  }, [selectedId, runs])

  // ---------------------------------------------------------------- events for the selected run
  const pullEvents = useCallback(async (runId: string) => {
    const since = lastIndex.current[runId]
    const page = await api.events(runId, since)
    if (page.events.length) {
      lastIndex.current[runId] = page.events[page.events.length - 1].index
      setEvents((ev) => ({ ...ev, [runId]: [...(since === undefined ? [] : ev[runId] ?? []), ...page.events] }))
    } else if (since === undefined) {
      lastIndex.current[runId] = page.last_index
      setEvents((ev) => ({ ...ev, [runId]: [] }))
    }
  }, [])

  useEffect(() => {
    if (selectedRun && events[selectedRun.team_run_id] === undefined) pullEvents(selectedRun.team_run_id).catch(() => {})
  }, [selectedRun, events, pullEvents])

  // Live polling while a run is going: new events + run status every 1.5 s.
  useEffect(() => {
    if (!busyRun) return
    const id = busyRun.team_run_id
    const tick = async () => {
      try {
        await pullEvents(id)
        const r = await api.run(id)
        if (r.status !== 'running') {
          await pullEvents(id)
          setRuns((rs) => ({ ...rs, [r.ticket_id]: r }))
          await refreshBoard()
          setSelectedId(r.ticket_id)
          setTab('summary')
          say(r.status === 'finished' ? `Ticket No. ${r.ticket_id} is back from the team. Have a look at the memo!` : 'That run hit a snag. Check the wire for details.')
        }
      } catch { /* keep polling */ }
    }
    const t = window.setInterval(tick, 1500)
    return () => window.clearInterval(t)
  }, [busyRun, pullEvents, refreshBoard])

  // ---------------------------------------------------------------- actions
  const startRun = async (ticketId: number) => {
    try {
      const r = await api.runTicket(ticketId)
      lastIndex.current[r.team_run_id] = -1
      setEvents((ev) => ({ ...ev, [r.team_run_id]: [] }))
      setRuns((rs) => ({ ...rs, [ticketId]: r }))
      setTab('wire')
      say('Off it goes! Watch the team pass slips around the table.')
    } catch (e) {
      alert((e as Error).message)
    }
  }

  const approve = async (a: Approval) => {
    const res = await api.approve(a.id, signer.trim(), pin.trim())
    await refreshBoard()
    if (selectedRun) await pullEvents(selectedRun.team_run_id).catch(() => {})
    if (res.done && res.paid) say(`Signed and cleared: ${money(Number(res.result.amount ?? 0))}. Beautiful penmanship!`)
    else if (res.done) say('Approved. The price is on record (no cash moves for a price).')
    else if (res.result.needs_second_approver) say('First signature in! This one needs a second, different person.')
    else throw new Error(`The pay tool refused it (practice ledger): ${String(res.result.message ?? 'refused')}`)
  }

  const decline = async (a: Approval, reason: string) => {
    await api.decline(a.id, signer.trim(), pin.trim(), reason)
    await refreshBoard()
    say('Declined, nothing paid. Saying no is part of the job, too.')
  }

  const closeTicket = async (t: Ticket) => {
    await api.setStatus(t.id, 'resolved', signer.trim() || 'desk')
    await refreshBoard()
    say(`Ticket No. ${t.id} is resolved. One more promise kept!`)
  }

  const reset = async () => {
    if (!confirm('Reset the shop to its original August 31 values? Payments, approvals, drafts and statuses from earlier runs are wiped from the working database (the audit trail keeps its history).')) return
    const usePin = pin.trim() || (prompt('Desk PIN (DESK_APPROVAL_PIN in .env):') ?? '').trim()
    if (!usePin) return
    try {
      await api.reset(usePin)
      setRuns({})
      setEvents({})
      lastIndex.current = {}
      localStorage.removeItem(OPENING_KEY)
      setOpening(null)
      setTab('wire')
      await refreshBoard()
      say('Fresh ledger, fresh start. Let’s go!')
    } catch (e) {
      alert((e as Error).message)
    }
  }

  // ---------------------------------------------------------------- derived view
  const runEvents = selectedRun ? events[selectedRun.team_run_id] ?? [] : []
  const activity = useMemo(() => deriveActivity(runEvents), [runEvents])
  const pending = approvals.filter((a) => a.status === 'pending' || a.status === 'partially_approved')
  const paid = approvals.filter((a) => a.status === 'approved' && a.kind !== 'price')
  const running = selectedRun?.status === 'running'
  const pendingForSelected = pending.filter((a) => a.ticket_id === selectedId).length

  return (
    <div className="desk">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>CC</span>
          <span>Campus Customs<small>Chapel Street Ops Desk</small></span>
        </div>
        <DeskCalendar iso={cash?.date_today} />
        <Ledger cash={cash} opening={cash?.opening_balance ?? opening} paid={paid} />
        <button className="btn btn-reset" onClick={reset} disabled={!!busyRun} title="Restore the original August 31 database">
          ↺ Reset the shop
        </button>
      </header>

      {offline && (
        <div className="offline">
          Can't reach the back office at <code>{API_URL}</code> ({offline}). Start it from <code>hw5/backend</code> with{' '}
          <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}

      <main className="floor">
        <TicketRail tickets={tickets} selectedId={selectedId} runs={runs} busyRun={busyRun} onSelect={setSelectedId} onRun={startRun} />

        <section className="center">
          {selectedTicket && (
            <div className="ticket-banner">
              <div>
                <span className="eyebrow">Ticket No. {selectedTicket.id} · {TICKET_KIND[selectedTicket.type] ?? selectedTicket.type}</span>
                <h1>{selectedTicket.subject}</h1>
              </div>
              <RunState run={selectedRun} ticket={selectedTicket} pendingCount={pendingForSelected} onClose={closeTicket} />
            </div>
          )}
          <TeamTable activity={activity} live={!!selectedRun} />
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'wire'} onClick={() => setTab('wire')}>
              The wire {running && <span className="live-dot" />}
            </button>
            <button role="tab" aria-selected={tab === 'summary'} onClick={() => setTab('summary')} disabled={!selectedRun}>
              Who did what
            </button>
          </div>
          <div className="tab-body">
            {tab === 'wire' ? <Wire events={runEvents} running={running} /> : <Summary activity={activity} run={selectedRun} drafts={detail?.drafts ?? []} />}
          </div>
        </section>

        <ApprovalTray pending={pending} signer={signer} onSigner={setSigner} pin={pin} onPin={setPin} onApprove={approve} onDecline={decline} />
      </main>

      <DanCorner cheer={cheer} />
    </div>
  )
}

function RunState({ run, ticket, pendingCount, onClose }: {
  run: Run | null; ticket: Ticket; pendingCount: number; onClose: (t: Ticket) => void
}) {
  if (ticket.status === 'resolved') {
    return <div className="run-state done"><span className="big-stamp">Resolved</span></div>
  }
  if (!run) return <div className="run-state">Not sent to the team yet</div>
  if (run.status === 'running') return <div className="run-state live"><span className="live-dot" /> Team at work since {new Date(run.started).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
  if (run.status === 'failed') return <div className="run-state bad">Run failed</div>
  return (
    <div className="run-state">
      <span>Run complete · the Boss left it <b>{STATUS_LABEL[ticket.status]}</b></span>
      {pendingCount > 0 ? (
        <span className="hint">✒ sign or decline in the tray first</span>
      ) : (
        <button className="btn btn-close" onClick={() => onClose(ticket)}>Mark resolved ✓</button>
      )}
    </div>
  )
}

function DeskCalendar({ iso }: { iso?: string }) {
  if (!iso) return <div className="calendar" />
  const d = new Date(`${iso}T12:00:00`)
  return (
    <div className="calendar" title="desk.date_today — the shop's 'today'">
      <span className="cal-dow">{d.toLocaleDateString('en-US', { weekday: 'short' })}</span>
      <span className="cal-day">{d.getDate()}</span>
      <span className="cal-mon">{d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span>
    </div>
  )
}
