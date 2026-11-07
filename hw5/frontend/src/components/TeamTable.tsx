import { AGENTS, SPECIALISTS, TOOL_LABELS } from '../agents'
import { clip } from '../derive'
import type { AgentActivity } from '../derive'
import type { Role } from '../types'

// The team table: the Boss at the head, four specialists seated below. Seats light up while
// an agent works, show who it's waiting on, its latest words and the tools it just used.
export default function TeamTable({ activity, live }: { activity: Record<Role, AgentActivity>; live: boolean }) {
  return (
    <section className="table-wrap" aria-label="The team">
      <div className="team-table">
        <Seat a={activity.boss} live={live} head />
        <div className="seats">
          {SPECIALISTS.map((r) => <Seat key={r} a={activity[r]} live={live} />)}
        </div>
      </div>
    </section>
  )
}

function Seat({ a, live, head = false }: { a: AgentActivity; live: boolean; head?: boolean }) {
  const m = AGENTS[a.role]
  const state = a.status === 'working' ? (a.waitingOn ? 'waiting' : 'working') : a.status
  const caption =
    state === 'working' ? 'thinking…' :
    state === 'waiting' ? `waiting on ${AGENTS[a.waitingOn!].name}` :
    state === 'done' ? 'done' : live ? 'not called (yet)' : 'at ease'
  return (
    <div className={`seat seat-${state}${head ? ' seat-head' : ''}`} style={{ '--agent': m.color } as React.CSSProperties}>
      <div className="seat-crest" aria-hidden>{m.monogram}</div>
      <div className="seat-body">
        <div className="seat-name">
          <b>{m.name}</b> <span>{m.title}</span>
        </div>
        <div className="seat-state">
          {state === 'working' && <span className="dots"><i /><i /><i /></span>}
          {caption}
          {a.calls > 1 && <span className="seat-count">called ×{a.calls}</span>}
        </div>
        {a.lastSaid && <p className={`seat-said voice-inline-${m.voice}`}>“{clip(a.lastSaid, head ? 170 : 110)}”</p>}
        {a.lastTools.length > 0 && (
          <div className="chips">
            {a.lastTools.map((t, i) => <span key={i} className="chip-tool">{TOOL_LABELS[t] ?? t}</span>)}
          </div>
        )}
      </div>
    </div>
  )
}
