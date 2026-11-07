import { useEffect, useRef } from 'react'
import Markdown from 'react-markdown'
import { AGENTS, TOOL_LABELS } from '../agents'
import { argsText, clip } from '../derive'
import type { DeskEvent, Role } from '../types'

// The live wire: every step of the run, newest at the bottom. Each agent's words are typeset in
// its own "voice" (memo, stockroom tag, ledger, notice, handwritten note) so you can tell who is
// talking at a glance; tool calls are small brass chips with their arguments.
export default function Wire({ events, running }: { events: DeskEvent[]; running: boolean }) {
  const box = useRef<HTMLOListElement>(null)
  useEffect(() => {
    // Scroll only the wire itself, so the team table stays in view while a run streams in.
    const el = box.current
    if (running && el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [events.length, running])

  if (events.length === 0) {
    return (
      <div className="wire-empty">
        <p className="hand">The wire is quiet.</p>
        <p>Pick a ticket on the board and send it to the team. Every message, tool call and hand-off shows up here as it happens.</p>
      </div>
    )
  }
  return (
    <ol className="wire" ref={box}>
      {events.map((e) => <WireItem key={e.index} e={e} />)}
      {running && <li className="wire-pending"><span className="dots"><i /><i /><i /></span> the team is working…</li>}
    </ol>
  )
}

function Who({ role }: { role: Role }) {
  const m = AGENTS[role]
  return <span className="who" style={{ '--agent': m.color } as React.CSSProperties}><i>{m.monogram}</i>{m.name}</span>
}

function WireItem({ e }: { e: DeskEvent }) {
  const time = new Date(e.ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })
  const indent = { '--depth': e.depth ?? 0 } as React.CSSProperties

  if (e.event === 'team_start') return <li className="wire-rule"><span>Run opened · {time}</span></li>
  if (e.event === 'team_end') return <li className="wire-rule"><span>Run closed · {time}</span></li>

  if (e.event === 'delegation' && e.agent) {
    const to = e.tools[0]?.args?.teammate as Role
    const req = (e.said ?? '').replace(/^Asked [^:]+:\s*/, '')
    return (
      <li className="wire-item slip" style={indent}>
        <div className="slip-head"><Who role={e.agent} /> <span className="arrow">passes a slip to</span> <Who role={to} /></div>
        <p className="slip-text">{clip(req, 360)}</p>
      </li>
    )
  }
  if (e.event === 'delegation_refused' && e.agent) {
    return <li className="wire-item muted" style={indent}><Who role={e.agent} /> {e.said}</li>
  }
  if (e.event === 'model_response' && e.agent) {
    if (e.tools.length === 0) return null // its words arrive with agent_end
    const tools = e.tools.filter((t) => t.tool !== 'ask_teammate')
    if (tools.length === 0) return null // shown as a slip instead
    return (
      <li className="wire-item uses" style={indent}>
        <Who role={e.agent} /> <span className="uses-verb">reaches for</span>
        {tools.map((t, i) => (
          <span key={i} className="chip-tool" title={JSON.stringify(t.args)}>
            {TOOL_LABELS[t.tool] ?? t.tool}{Object.keys(t.args).length > 0 && <em>{clip(argsText(t.args), 40)}</em>}
          </span>
        ))}
        {e.said && <p className="aside">{clip(e.said, 240)}</p>}
      </li>
    )
  }
  if (e.event === 'model_request' && e.agent) {
    const rows = e.tool_results.filter((r) => r.tool !== 'ask_teammate')
    if (rows.length === 0) return null
    return (
      <li className="wire-item results" style={indent}>
        <details>
          <summary>↳ {rows.length} tool result{rows.length > 1 ? 's' : ''} back to {AGENTS[e.agent].name}</summary>
          {rows.map((r, i) => (
            <pre key={i}><b>{TOOL_LABELS[r.tool] ?? r.tool}</b> {clip(r.result, 420)}</pre>
          ))}
        </details>
      </li>
    )
  }
  if (e.event === 'agent_end' && e.agent && e.said) {
    const m = AGENTS[e.agent]
    return (
      <li className="wire-item said" style={indent}>
        <div className="said-head"><Who role={e.agent} /> <span className="voice-label">{m.voiceLabel}</span> <time>{time}</time></div>
        <div className={`voice voice-${m.voice}`} style={{ '--agent': m.color } as React.CSSProperties}>
          <Markdown>{e.said}</Markdown>
        </div>
      </li>
    )
  }
  if (e.event === 'approval_prepared') {
    return (
      <li className="wire-item sign" style={indent}>
        ✒ {e.agent && <Who role={e.agent} />} prepared <b>{e.said?.replace(/^Prepared for a human: /, '')}</b>. It is in your signature tray, and nothing has moved yet.
      </li>
    )
  }
  if (e.event === 'approval_refused') {
    return <li className="wire-item muted" style={indent}>{e.agent && <Who role={e.agent} />} could not prepare it: {e.said}</li>
  }
  if (e.event === 'paused_for_approval' || e.event === 'approval_queued') return null
  if (e.event.startsWith('payment_') || e.event === 'approval_signed' || e.event === 'approval_partly_signed' || e.event === 'ticket_status') {
    return <li className={`wire-item human ${e.event}`}>☞ <b>You</b> · {e.said}</li>
  }
  if (e.event === 'error') return <li className="wire-item error">Something went wrong: {e.said}</li>
  return null
}
