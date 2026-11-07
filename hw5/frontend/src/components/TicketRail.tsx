import { STATUS_LABEL, TICKET_KIND } from '../agents'
import type { Run, Ticket } from '../types'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  runs: Record<number, Run>
  busyRun: Run | null
  onSelect: (id: number) => void
  onRun: (id: number) => void
}

// Left rail: the three tickets as perforated claim stubs with a rubber status stamp.
export default function TicketRail({ tickets, selectedId, runs, busyRun, onSelect, onRun }: Props) {
  return (
    <section className="rail" aria-label="Ticket board">
      <h2 className="panel-title">The Board <small>{tickets.filter((t) => t.state === 'open').length} open</small></h2>
      {tickets.map((t) => {
        const run = runs[t.id]
        const running = run?.status === 'running'
        const selected = t.id === selectedId
        return (
          <article
            key={t.id}
            className={`stub kind-${t.type}${selected ? ' selected' : ''}${running ? ' running' : ''}`}
            onClick={() => onSelect(t.id)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(t.id)}
            tabIndex={0}
            role="button"
            aria-pressed={selected}
          >
            <div className="stub-top">
              <span className="stub-no">No. {t.id}</span>
              <span className="stub-kind">{TICKET_KIND[t.type] ?? t.type}</span>
            </div>
            <h3>{t.subject}</h3>
            <p className="stub-from">from <b>{t.requester}</b></p>
            {t.sku && (
              <p className="stub-facts">
                <span>{t.sku}</span>
                {t.size && <span>size {t.size}</span>}
                {t.qty != null && <span>× {t.qty}</span>}
              </p>
            )}
            <span className={`stamp stamp-${t.status}`}>{STATUS_LABEL[t.status] ?? t.status}</span>
            {t.pending_approvals > 0 && <span className="sig-flag">✒ {t.pending_approvals} to sign</span>}
            {selected && (
              <button
                className="btn btn-run"
                disabled={!!busyRun}
                onClick={(e) => { e.stopPropagation(); onRun(t.id) }}
                title={busyRun ? `Ticket ${busyRun.ticket_id} is being worked right now` : 'Start the agent team on this ticket'}
              >
                {running ? 'Team at work…' : busyRun ? `Desk busy with No. ${busyRun.ticket_id}` : run ? 'Send to the team again' : 'Send to the team →'}
              </button>
            )}
            {run && !selected && (
              <span className="stub-run">{running ? 'team at work…' : run.status === 'finished' ? 'run complete' : 'run failed'}</span>
            )}
          </article>
        )
      })}
    </section>
  )
}
