import Markdown from 'react-markdown'
import { AGENTS, ROLES, TOOL_LABELS } from '../agents'
import { clip, plain } from '../derive'
import type { AgentActivity } from '../derive'
import type { Draft, Role, Run } from '../types'

// After a run: one receipt per agent (who called it, what it did, which tools, its last word),
// then the Boss's full memo. Agents that weren't needed say so, which is the point.
export default function Summary({ activity, run, drafts }: { activity: Record<Role, AgentActivity>; run: Run | null; drafts: Draft[] }) {
  if (!run) return <div className="wire-empty"><p className="hand">No run yet for this ticket.</p></div>
  return (
    <div className="summary">
      <div className="receipts">
        {ROLES.map((r) => <Receipt key={r} a={activity[r]} />)}
      </div>
      {run.report && (
        <article className="memo">
          <header>
            <span className="memo-kicker">Memorandum</span>
            <h3>From the Boss · Ticket No. {run.ticket_id}</h3>
            <p className="memo-meta">
              {run.delegations ?? 0} hand-offs · {run.requests ?? 0} model calls · {(run.total_tokens ?? 0).toLocaleString()} tokens
            </p>
          </header>
          <Markdown>{run.report}</Markdown>
        </article>
      )}
      {drafts.length > 0 && (
        <section className="drafts" aria-label="Drafts on this ticket">
          <h3>Drafts on the board <small>never sent</small></h3>
          {drafts.map((d) => (
            <article key={d.id} className={`draft draft-${d.audience}`}>
              <span className="draft-tag">{d.audience === 'customer' ? 'To the requester' : 'Internal note: team only'}</span>
              <p>{d.text}</p>
            </article>
          ))}
        </section>
      )}
      {run.error && <p className="error-note">The run failed: {run.error}</p>}
    </div>
  )
}

function Receipt({ a }: { a: AgentActivity }) {
  const m = AGENTS[a.role]
  const style = { '--agent': m.color } as React.CSSProperties
  if (a.calls === 0) {
    return (
      <div className="receipt receipt-idle" style={style}>
        <div className="receipt-head"><i>{m.monogram}</i>{m.name}</div>
        <p className="receipt-none">Not called on this ticket.</p>
      </div>
    )
  }
  const tools = Object.entries(a.toolsUsed).filter(([t]) => t !== 'ask_teammate')
  const by = [...new Set(a.askedBy)].map((r) => AGENTS[r].name)
  const asked = [...new Set(a.asked)].map((r) => AGENTS[r].name)
  return (
    <div className="receipt" style={style}>
      <div className="receipt-head"><i>{m.monogram}</i>{m.name}</div>
      <dl>
        {a.role !== 'boss' && <><dt>Called by</dt><dd>{by.join(', ') || '—'}{a.calls > 1 ? ` (×${a.calls})` : ''}</dd></>}
        <dt>Asked</dt><dd>{asked.join(', ') || 'no one'}</dd>
        <dt>Tools</dt>
        <dd className="chips">
          {tools.length === 0 ? '—' : tools.map(([t, n]) => (
            <span key={t} className="chip-tool">{TOOL_LABELS[t] ?? t}{n > 1 && <em>×{n}</em>}</span>
          ))}
        </dd>
      </dl>
      {a.finalWords && <p className="receipt-words">“{clip(plain(a.finalWords), a.role === 'boss' ? 200 : 260)}”</p>}
    </div>
  )
}
