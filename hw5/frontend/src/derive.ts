import { ROLES } from './agents'
import type { DeskEvent, Role } from './types'

export interface AgentActivity {
  role: Role
  status: 'idle' | 'working' | 'done'
  calls: number            // times this agent was started on the ticket
  responses: number        // model turns
  active: number           // agent loops currently running
  lastSaid: string | null  // latest words (plain text)
  lastTools: string[]      // tools in its latest turn
  toolsUsed: Record<string, number>
  asked: Role[]            // teammates it delegated to
  askedBy: Role[]          // who delegated to it
  waitingOn: Role | null   // the teammate it is waiting for right now
  finalWords: string | null
}

export function emptyActivity(): Record<Role, AgentActivity> {
  return Object.fromEntries(ROLES.map((r) => [r, {
    role: r, status: 'idle', calls: 0, responses: 0, active: 0, lastSaid: null, lastTools: [],
    toolsUsed: {}, asked: [], askedBy: [], waitingOn: null, finalWords: null,
  }])) as unknown as Record<Role, AgentActivity>
}

/** Replay a run's events into "what is each agent doing / what did it do". */
export function deriveActivity(events: DeskEvent[]): Record<Role, AgentActivity> {
  const a = emptyActivity()
  for (const e of events) {
    const me = e.agent ? a[e.agent] : null
    if (!me) continue
    switch (e.event) {
      case 'agent_start':
        me.calls += 1
        me.active += 1
        me.status = 'working'
        break
      case 'agent_end':
        me.active = Math.max(0, me.active - 1)
        me.finalWords = e.said
        me.lastSaid = plain(e.said)
        if (me.active === 0) me.status = 'done'
        me.waitingOn = null
        break
      case 'model_response':
        me.responses += 1
        me.lastTools = e.tools.map((t) => t.tool)
        for (const t of e.tools) me.toolsUsed[t.tool] = (me.toolsUsed[t.tool] ?? 0) + 1
        if (e.said) me.lastSaid = plain(e.said)
        break
      case 'model_request':
        me.waitingOn = null
        break
      case 'delegation': {
        const to = (e.tools[0]?.args?.teammate as Role | undefined) ?? null
        if (to) {
          me.asked.push(to)
          a[to].askedBy.push(me.role)
          me.waitingOn = to
        }
        break
      }
    }
  }
  return a
}

/** Markdown → one plain line, for previews. */
export function plain(md: string | null | undefined): string | null {
  if (!md) return null
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`|]/g, '')
    .replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

export function clip(s: string | null | undefined, n: number): string {
  if (!s) return ''
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s
}

export function argsText(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([k]) => k !== 'request')
    .map(([, v]) => (typeof v === 'object' ? JSON.stringify(v) : String(v)))
    .join(' · ')
}
